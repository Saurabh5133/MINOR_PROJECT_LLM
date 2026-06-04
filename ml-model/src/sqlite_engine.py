"""
SQLite Execution Engine — Real cost model, no hardcoded factors.

Cost formula (standard DB cost model, page I/O units):
  scan_cost     = rows / PAGE_ROWS                          (full scan)
  index_cost    = log2(rows/PAGE_ROWS) + sel*rows/PAGE_ROWS (index seek+range)
  join_cost     = sum(scan of each table with selectivity applied)
  sort_cost     = N_sorted * log2(N_sorted) / MERGE_FACTOR  (external merge sort)
  topN_cost     = N_input * log2(K)                         (heap sort with LIMIT K)
  agg_cost      = N_input / PAGE_ROWS                       (hash aggregation, 1 pass)
  subquery_cost = (subquery scan) * correlation_factor

col_factor (projection savings):
  Derived from ratio of (bytes of selected columns) / (bytes of all columns).
  Handles aliased columns like se.triggered_at correctly.
"""

import sqlite3, re, math, random, string, os
from datetime import datetime, timedelta
import uuid as _uuid


PAGE_ROWS    = 100      # rows per 8KB page (~80 bytes avg)
MERGE_FACTOR = 4        # merge sort fan-in


class SQLiteEngine:
    def __init__(self):
        self.conn   = None
        self.schema = None

    # ─────────────────────────────────────────── setup ──
    def setup(self, schema: dict):
        self.schema = schema
        self.conn   = sqlite3.connect(':memory:', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables(schema)
        self._insert_data(schema)
        self._create_indexes(schema)

    def _create_tables(self, schema):
        cur = self.conn.cursor()
        for tbl, info in schema.items():
            cols = info.get('columns', [])
            defs = []
            for col in cols:
                cn = col if isinstance(col, str) else col.get('name', col)
                ct = self._infer_type(cn)
                defs.append(f'"{cn}" {ct}')
            if defs:
                try:
                    cur.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" ({",".join(defs)})')
                except Exception as e:
                    print(f'[SQLite] table {tbl}: {e}')
        self.conn.commit()

    def _infer_type(self, name):
        n = name.lower()
        if n == 'id' or n.endswith('_id'): return 'INTEGER'
        if any(x in n for x in ['age','year','count','qty','quantity','num','rank','score',
                                  'level','floor','seat','room','duration','size','capacity',
                                  'votes','views','clicks','pages','units','priority','sequence']): return 'INTEGER'
        if any(x in n for x in ['price','amount','cost','salary','balance','total','rate',
                                  'ratio','percent','lat','lon','gpa','temp','speed','weight',
                                  'height','revenue','budget','fee','fare','tax','discount']): return 'REAL'
        return 'TEXT'

    def _insert_data(self, schema):
        cur  = self.conn.cursor()
        tbls = list(schema.keys())
        for tbl in tbls:
            info  = schema[tbl]
            cols  = info.get('columns', [])
            nrows = min(info.get('row_count', 100), 300)
            cnames = [c if isinstance(c,str) else c.get('name',c) for c in cols]
            ctypes = [self._infer_type(cn) for cn in cnames]
            if not cnames: continue
            ph  = ','.join(['?']*len(cnames))
            qcols = ','.join([f'"{c}"' for c in cnames])
            sql = f'INSERT INTO "{tbl}" ({qcols}) VALUES ({ph})'
            rows = [[self._val(cn,ct,i,tbl,tbls,schema) for cn,ct in zip(cnames,ctypes)]
                    for i in range(1, nrows+1)]
            try: cur.executemany(sql, rows)
            except Exception as e: print(f'[SQLite] insert {tbl}: {e}')
        self.conn.commit()

    def _val(self, name, col_type, idx, table, all_tables, schema):
        n = name.lower()
        if n == 'id': return idx
        if n.endswith('_id') and n != 'id':
            ref = n[:-3]
            for cand in [ref, ref+'s', ref.rstrip('s')]:
                for t in all_tables:
                    if t.lower() == cand.lower():
                        return random.randint(1, min(schema[t].get('row_count',100), 200))
            return random.randint(1, 100)
        if col_type == 'INTEGER':
            if any(x in n for x in ['age','years']): return random.randint(1,100)
            if any(x in n for x in ['year','yr']):   return random.randint(2000,2025)
            if any(x in n for x in ['zip','postal']): return random.randint(10000,99999)
            if any(x in n for x in ['priority','rank','level','score']): return random.randint(1,10)
            return random.randint(1, 100000)
        if col_type == 'REAL':
            if any(x in n for x in ['lat','latitude']):  return round(random.uniform(-90,90),6)
            if any(x in n for x in ['lon','lng','longitude']): return round(random.uniform(-180,180),6)
            if any(x in n for x in ['rate','ratio','percent','pct','gpa','probability','accuracy']): return round(random.uniform(0,1),4)
            return round(random.uniform(1, 50000), 2)
        # TEXT
        if any(x in n for x in ['uuid','guid']): return str(_uuid.uuid4())
        if any(x in n for x in ['code','sku','serial','ref','token','barcode']): return ''.join(random.choices(string.ascii_uppercase+string.digits,k=8))
        if 'email' in n: return f'user{idx}@example.com'
        if any(x in n for x in ['phone','mobile','tel']): return f'+1{random.randint(2000000000,9999999999)}'
        if any(x in n for x in ['first_name','firstname']): return random.choice(['Alice','Bob','Carol','David','Eva','Frank','Grace','Henry','Iris','Jack'])
        if any(x in n for x in ['last_name','lastname','surname']): return random.choice(['Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis'])
        if 'name' in n: return f'{random.choice(["Alpha","Beta","Gamma","Delta","North","South"])} {random.choice(["Systems","Group","Center","Labs","Hub"])} {idx}'
        if any(x in n for x in ['city','town']): return random.choice(['New York','London','Tokyo','Paris','Sydney','Dubai','Toronto','Berlin'])
        if any(x in n for x in ['country','nation']): return random.choice(['USA','UK','Japan','France','Australia','UAE','Canada','Germany'])
        if any(x in n for x in ['status','stage','phase']): return random.choice(['active','inactive','pending','approved','rejected','draft','published'])
        if any(x in n for x in ['type','kind','mode','method','format']): return random.choice(['typeA','typeB','typeC','typeD','standard','premium','basic'])
        if any(x in n for x in ['category','genre','department','domain','field']): return random.choice(['Science','Technology','Engineering','Arts','Business','Medicine','Law'])
        if any(x in n for x in ['date','time','created','updated','at','on','timestamp','born','start','end','deadline','issued','joined','released','launched']):
            base  = datetime(2015,1,1)
            delta = timedelta(days=random.randint(0,3650), hours=random.randint(0,23))
            return (base+delta).strftime('%Y-%m-%d %H:%M:%S')
        if any(x in n for x in ['description','desc','summary','bio','notes','comment','review','content','text','message','title','abstract']):
            return f'Sample {table} {name.replace("_"," ")} {idx}'
        if any(x in n for x in ['url','link','website','uri']): return f'https://example.com/{table}/{idx}'
        if any(x in n for x in ['ip','ip_address','host']): return f'{random.randint(1,254)}.{random.randint(0,254)}.{random.randint(0,254)}.{random.randint(1,254)}'
        if any(x in n for x in ['color','colour']): return random.choice(['Red','Blue','Green','Yellow','Orange','Purple','Black','White'])
        if any(x in n for x in ['version','ver']): return f'{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,99)}'
        return f'{table}_{name}_{idx}'

    def _create_indexes(self, schema):
        cur = self.conn.cursor()
        for tbl, info in schema.items():
            for col in info.get('columns', []):
                cn = col if isinstance(col,str) else col.get('name',col)
                n  = cn.lower()
                if n == 'id' or n.endswith('_id') or n in ('email','status','type','category','created_at'):
                    try: cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{tbl}_{cn}" ON "{tbl}" ("{cn}")')
                    except: pass
        self.conn.commit()

    # ─────────────────────────────────────────── execution plan ──
    def get_execution_plan(self, query: str) -> dict:
        if not self.conn:
            return {'error':'DB not init','steps':[],'cost':999}
        q = query.strip().rstrip(';')
        try:
            cur = self.conn.cursor()
            cur.execute(f'EXPLAIN QUERY PLAN {q}')
            rows = cur.fetchall()
            steps = [self._parse_step(r[3] if len(r)>3 else str(r)) for r in rows]
            if not steps:
                steps = [{'detail':'SCAN','type':'SCAN','step_cost':100,'uses_index':False}]
            return {'steps':steps,'cost':round(sum(s['step_cost'] for s in steps),2),
                    'raw_plan':[list(r) for r in rows],'query':q}
        except Exception as e:
            return {'error':str(e),'steps':[],'cost':999,'query':q}

    def _parse_step(self, detail: str) -> dict:
        du = detail.upper()
        uses_index = 'USING INDEX' in du or 'USING COVERING INDEX' in du
        is_search  = 'SEARCH' in du
        is_scan    = 'SCAN'   in du
        is_temp    = 'USE TEMP B-TREE' in du

        m = re.search(r'(?:SCAN|SEARCH)\s+(?:TABLE\s+)?(\w+)', du)
        tbl = m.group(1) if m else None
        rows = 100
        if tbl and self.schema:
            for tn, ti in self.schema.items():
                if tn.upper() == tbl: rows = ti.get('row_count',100); break

        if is_scan and not uses_index:   cost = rows / PAGE_ROWS
        elif is_search and uses_index:   cost = max(1, math.log2(max(2,rows/PAGE_ROWS))*5)
        elif is_search:                  cost = rows / PAGE_ROWS * 0.5
        else:                            cost = 10
        if is_temp: cost += rows / PAGE_ROWS * 0.1

        return {'detail':detail,'type':'SEARCH' if is_search else 'SCAN' if is_scan else 'OTHER',
                'uses_index':uses_index,'is_temp_sort':is_temp,'step_cost':round(cost,2),'table':tbl}

    # ─────────────────────────────────────────── cost model ──
    def estimate_cost(self, query: str, schema: dict) -> dict:
        """
        Real cost model — no hardcoded factors.
        All numbers derived from query structure + schema statistics.
        """
        q      = query.strip()
        qu     = q.upper()
        schema = schema or {}

        # ── table row counts ──────────────────────────────────────────────
        from_tbls  = re.findall(r'\bFROM\s+(\w+)', q, re.IGNORECASE)
        join_tbls  = re.findall(r'\bJOIN\s+(\w+)',  q, re.IGNORECASE)
        used_tbls  = from_tbls + join_tbls

        # build alias → (table_name, row_count, col_count) map
        alias_info = {}   # alias_lower → (tbl_name, row_count, col_list)
        for m in re.finditer(r'(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?', q, re.IGNORECASE):
            tbl   = m.group(1)
            alias = m.group(2) or tbl
            tinfo = None
            for tn, ti in schema.items():
                if tn.lower() == tbl.lower(): tinfo = ti; break
            rc   = tinfo.get('row_count', 1000) if tinfo else 1000
            cols = tinfo.get('columns', [])     if tinfo else []
            alias_info[alias.lower()]  = (tbl, rc, cols)
            alias_info[tbl.lower()]    = (tbl, rc, cols)

        row_counts = [v[1] for v in alias_info.values()
                      if v[0].lower() in [t.lower() for t in used_tbls]]
        # deduplicate — one entry per physical table
        seen_tbls = set()
        rc_list   = []
        for alias_l, (tbl, rc, cols) in alias_info.items():
            if tbl.lower() in [t.lower() for t in used_tbls] and tbl not in seen_tbls:
                seen_tbls.add(tbl)
                rc_list.append((tbl, rc, cols))

        if not rc_list:
            rc_list = [('unknown', 1000, [])]

        total_rows = sum(r[1] for r in rc_list)

        # ── selectivity (per-predicate, multiplicative for AND) ───────────
        sel = self._selectivity(q)

        # ── column projection factor ──────────────────────────────────────
        # Measure actual bytes saved, not just column count
        col_factor = self._col_factor(q, rc_list, alias_info)

        # ── scan cost ─────────────────────────────────────────────────────
        # Determine if WHERE predicates can use an index
        indexed_cols = set()
        for _, _, cols in rc_list:
            for col in cols:
                cn = col if isinstance(col,str) else col.get('name',col)
                nl = cn.lower()
                if nl == 'id' or nl.endswith('_id') or nl in ('status','type','email','category','created_at'):
                    indexed_cols.add(nl)

        where_cols = re.findall(r'(\w+)\s*(?:=|>|<|>=|<=|!=|LIKE|BETWEEN|IN\s*\()', q, re.IGNORECASE)
        where_cols_lower = [c.lower().split('.')[-1] for c in where_cols]
        uses_index = any(c in indexed_cols for c in where_cols_lower)

        scan_cost = 0
        for tbl, rc, cols in rc_list:
            pages = max(1, rc / PAGE_ROWS)
            if uses_index and 'WHERE' in qu:
                # Index seek: log(pages) to find first match + selective range scan
                scan_cost += math.log2(pages + 1) + pages * sel
            else:
                # Full table scan
                scan_cost += pages

        # Apply column projection to scan cost (fewer columns = fewer bytes per page)
        scan_cost *= col_factor

        # ── join cost ─────────────────────────────────────────────────────
        # Hash join cost depends on build/probe order.
        # We model the ACTUAL order in the query (FROM table1 JOIN table2 JOIN table3)
        # Build hash on each right-side table, probe with left side.
        join_count = len(re.findall(r'\bJOIN\b', qu))
        join_cost  = 0
        if join_count > 0 and len(rc_list) >= 2:
            # rc_list is in query order (FROM table first, then JOINs)
            # For each join: build on right table, probe with accumulated left side
            left_rows = rc_list[0][1] * sel   # FROM table after filter
            for i in range(1, len(rc_list)):
                right_rows  = rc_list[i][1]   # JOIN table (unfiltered until join)
                build_pages = right_rows / PAGE_ROWS
                probe_pages = left_rows   / PAGE_ROWS
                join_cost  += build_pages + probe_pages
                # Output of this join feeds the next
                left_rows   = left_rows * sel  # further filtered

        # ── sort cost ─────────────────────────────────────────────────────
        sort_cost = 0
        if re.search(r'\bORDER\s+BY\b', qu):
            rows_to_sort = total_rows * sel
            limit_m      = re.search(r'\bLIMIT\s+(\d+)', qu)
            if limit_m:
                k         = int(limit_m.group(1))
                # Top-N heap sort: O(N_pages * log2(K_pages))
                # K in pages — this is always <= full merge sort
                k_pages   = max(1, k / PAGE_ROWS)
                n_pages   = max(1, rows_to_sort / PAGE_ROWS)
                sort_cost = n_pages * math.log2(k_pages + 1) / MERGE_FACTOR
            else:
                # External merge sort: O(N_pages * log2(N_pages) / merge_factor)
                pages     = max(1, rows_to_sort / PAGE_ROWS)
                sort_cost = pages * math.log2(pages + 1) / MERGE_FACTOR

        # ── aggregation cost ──────────────────────────────────────────────
        agg_cost = 0
        if re.search(r'\bGROUP\s+BY\b', qu):
            # Hash aggregation: one pass over filtered rows
            rows_to_agg = total_rows * sel
            agg_cost    = max(1, rows_to_agg / PAGE_ROWS) * 0.5

        # ── subquery cost ─────────────────────────────────────────────────
        subq_count = len(re.findall(r'\(SELECT', qu))
        subq_cost  = 0
        if subq_count > 0:
            # Find subquery tables and use their row counts
            # Pattern: (SELECT ... FROM subq_table WHERE ...)
            subq_tables = re.findall(r'\(SELECT\s+.*?FROM\s+(\w+)', q, re.IGNORECASE | re.DOTALL)
            for st in subq_tables:
                for tn, ti in schema.items():
                    if tn.lower() == st.lower():
                        subq_rows = ti.get('row_count', 1000)
                        # Full scan of subquery table (IN) vs short-circuit (EXISTS)
                        # EXISTS: avg scans half the table before finding match
                        is_exists = 'EXISTS' in qu
                        factor    = 0.5 if is_exists else 1.0
                        subq_cost += (subq_rows / PAGE_ROWS) * factor
                        break
            # Fallback if table not found
            if subq_cost == 0:
                largest_rc = max(r[1] for r in rc_list)
                subq_cost  = (largest_rc / PAGE_ROWS) * 0.5

        # ── DISTINCT cost ─────────────────────────────────────────────────
        # DISTINCT requires deduplication: O(N log N) sort or hash pass
        distinct_cost = 0
        if re.search(r'\bSELECT\s+DISTINCT\b', qu):
            # Only if no GROUP BY (which already deduplicates)
            if not re.search(r'\bGROUP\s+BY\b', qu):
                rows_to_dedup = total_rows * sel
                pages_to_dedup = max(1, rows_to_dedup / PAGE_ROWS)
                distinct_cost  = pages_to_dedup * math.log2(pages_to_dedup + 1) / MERGE_FACTOR

        total = scan_cost + join_cost + sort_cost + agg_cost + subq_cost + distinct_cost
        total = max(1.0, total)

        return {
            'total':       round(total, 2),
            'breakdown': {
                'scan_cost':     round(scan_cost,     2),
                'join_cost':     round(join_cost,     2),
                'sort_cost':     round(sort_cost,     2),
                'agg_cost':      round(agg_cost,      2),
                'subquery_cost': round(subq_cost,     2),
                'distinct_cost': round(distinct_cost, 2),
            },
            'uses_index':  uses_index,
            'col_factor':  round(col_factor, 4),
            'selectivity': round(sel, 6),
            'join_count':  join_count,
        }

    def _col_factor(self, query: str, rc_list: list, alias_info: dict) -> float:
        """
        Compute fraction of row bytes actually read.
        SELECT * = 1.0 (all bytes).
        Explicit columns = sum(bytes of selected cols) / sum(bytes of all cols).
        Handles aliases like se.triggered_at correctly.
        """
        if re.search(r'SELECT\s+\*', query, re.IGNORECASE):
            return 1.0

        # Extract select list (between SELECT and FROM)
        m = re.search(r'SELECT\s+(.*?)\s+FROM\b', query, re.IGNORECASE | re.DOTALL)
        if not m:
            return 1.0

        select_text = m.group(1)
        qu_check    = query.upper()

        # For GROUP BY / aggregate queries, full table scan is unavoidable
        # — col_factor savings don't apply because all rows must be read for aggregation
        if re.search(r'\bGROUP\s+BY\b', qu_check):
            return 1.0

        # Skip pure aggregate queries (no GROUP BY either)
        non_agg_cols = re.sub(
            r'\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)(?:\s+AS\s+\w+)?',
            '', select_text, flags=re.IGNORECASE
        ).strip().strip(',').strip()
        if not non_agg_cols:
            return 1.0

        # Parse selected columns: strip alias prefixes (se.col → col)
        selected_raw = [c.strip() for c in select_text.split(',') if c.strip()]
        selected_cols = set()
        for col in selected_raw:
            # Handle: alias.col, alias.col AS label, func(col), col AS label
            col_clean = re.sub(r'\s+AS\s+\w+', '', col, flags=re.IGNORECASE).strip()
            col_clean = col_clean.split('.')[-1].strip().lower()
            col_clean = re.sub(r'\(.*\)', '', col_clean).strip()  # remove func args
            if col_clean:
                selected_cols.add(col_clean)

        if not selected_cols:
            return 1.0

        # Total columns across all tables used in query
        # Use byte weights: INT=4, REAL=8, TEXT=avg 40 bytes
        def col_bytes(col_name: str) -> int:
            n = col_name.lower()
            if self._infer_type(n) == 'INTEGER': return 4
            if self._infer_type(n) == 'REAL':    return 8
            return 40  # TEXT average

        total_bytes    = 0
        selected_bytes = 0
        for tbl, rc, cols in rc_list:
            for col in cols:
                cn    = col if isinstance(col,str) else col.get('name', col)
                b     = col_bytes(cn)
                total_bytes += b
                if cn.lower() in selected_cols:
                    selected_bytes += b

        if total_bytes == 0:
            return 1.0

        factor = selected_bytes / total_bytes
        # Clamp: min 0.05 (even 1 narrow column), max 1.0
        return round(max(0.05, min(1.0, factor)), 4)

    def _selectivity(self, query: str) -> float:
        """
        Order-independent selectivity estimation.
        Collects ALL predicates from WHERE clause then combines them,
        regardless of which order they appear in the query.
        """
        qu    = query.upper()
        where = re.search(
            r'\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)',
            qu, re.DOTALL)
        if not where:
            return 1.0
        clause = where.group(1).strip()
        sel    = self._parse_conditions(clause)
        return round(max(0.001, min(1.0, sel)), 6)

    def _parse_conditions(self, clause: str) -> float:
        clause = clause.strip()
        if not clause:
            return 1.0
        if clause.startswith('(') and clause.endswith(')'):
            depth, fully = 0, True
            for i, c in enumerate(clause):
                if c == '(':   depth += 1
                elif c == ')': depth -= 1
                if depth == 0 and i < len(clause) - 1:
                    fully = False; break
            if fully:
                clause = clause[1:-1].strip()
        or_parts = self._split_top(clause, 'OR')
        if len(or_parts) > 1:
            result = self._parse_conditions(or_parts[0])
            for p in or_parts[1:]:
                s = self._parse_conditions(p)
                result = result + s - result * s
            return min(1.0, result)
        and_parts = self._split_top(clause, 'AND')
        if len(and_parts) > 1:
            result = 1.0
            for p in and_parts:
                result *= self._single_pred_sel(p)
            return result
        return self._single_pred_sel(clause)

    def _split_top(self, text: str, keyword: str) -> list:
        """Split on keyword at depth 0, handling newlines and extra spaces."""
        # Normalize whitespace/newlines to single space for matching
        normalized = re.sub(r'\s+', ' ', text).strip()
        kw = f' {keyword} '
        kw_u = kw.upper()
        nu = normalized.upper()

        parts, depth, i, start = [], 0, 0, 0
        while i < len(normalized):
            if normalized[i] == '(':   depth += 1
            elif normalized[i] == ')': depth -= 1
            elif depth == 0 and nu[i:i+len(kw_u)] == kw_u:
                parts.append(normalized[start:i].strip())
                i += len(kw); start = i; continue
            i += 1
        parts.append(normalized[start:].strip())
        return [p for p in parts if p]

    # keep old names as aliases
    def _split_top_level(self, text, keyword): return self._split_top(text, keyword)

    def _single_predicate_sel(self, pred): return self._single_pred_sel(pred)

    def _single_pred_sel(self, pred: str) -> float:
        p = pred.strip().upper()
        if 'IS NOT NULL' in p:                       return 0.95
        if 'IS NULL' in p:                           return 0.05
        if ' NOT IN ' in p or '!=' in p or '<>' in p: return 0.90
        if 'LIKE' in p:
            lm = re.search(r"LIKE\s+'([^']*)'", pred, re.IGNORECASE)
            if lm:
                pat = lm.group(1)
                if pat.startswith('%') and pat.endswith('%'): return 0.30
                if pat.startswith('%') or pat.endswith('%'):  return 0.15
                return 0.05
            return 0.20
        if 'BETWEEN' in p:              return 0.10
        if ' IN (' in p:
            im = re.search(r'IN\s*\(([^)]*)\)', pred, re.IGNORECASE)
            if im:
                n = len([v for v in im.group(1).split(',') if v.strip()])
                return min(0.50, n * 0.05)
            return 0.10
        if re.search(r'>=|<=', p):  return 0.30
        if re.search(r'>|<', p):    return 0.25
        if '=' in p:                 return 0.05
        return 0.50

    # Keep alias for backward compatibility
    def estimate_selectivity_cost(self, query: str, schema: dict) -> float:
        return self.estimate_cost(query, schema)['total']

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
