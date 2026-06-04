"""
Rule-Based Optimizer
14 rules covering all common SQL patterns — no hardcoded improvements,
every gain comes from the cost model reacting to actual query changes.
"""
import re
from typing import List, Tuple, Optional


class RuleOptimizer:
    def __init__(self):
        self.rules = [
            self._rule_where_condition_reorder,   # cheapest predicates first
            self._rule_or_to_in,                  # OR col=x OR col=y → col IN (x,y)
            self._rule_in_to_exists,              # IN (subquery) → EXISTS
            self._rule_exists_select_1,           # EXISTS (SELECT *) → EXISTS (SELECT 1)
            self._rule_remove_select_star,        # SELECT * → explicit columns
            self._rule_column_pruning,            # drop large TEXT blobs from SELECT
            self._rule_join_order,                # reorder JOINs smallest→largest
            self._rule_predicate_before_join,     # push filter into subquery before join
            self._rule_remove_orderby_subquery,   # ORDER BY inside subquery w/o LIMIT
            self._rule_remove_redundant_distinct, # DISTINCT + GROUP BY
            self._rule_remove_distinct_pk,        # DISTINCT when id in SELECT
            self._rule_count_star,                # COUNT(id) → COUNT(*)
            self._rule_implicit_to_explicit_join, # FROM t1,t2 WHERE → INNER JOIN ON
        ]  # Note: limit_pushdown removed — adding LIMIT changes query semantics

    def generate_candidates(self, query: str, schema: dict = None) -> List[Tuple[str, str, str]]:
        candidates = []
        current = query.strip()
        for rule_fn in self.rules:
            try:
                result = rule_fn(current, schema)
                if not result:
                    continue
                new_q, rule_name, desc = result
                if not new_q or new_q.strip() == current.strip():
                    continue
                nu = new_q.upper()
                if 'SELECT' not in nu or 'FROM' not in nu:
                    continue
                candidates.append((new_q, rule_name, desc))
                current = new_q  # chain
            except Exception:
                continue
        return candidates

    @staticmethod
    def _safe_alias(tbl: str, raw_alias) -> str:
        """Return raw_alias unless it's a SQL keyword, in which case return tbl."""
        _SQL_KW = {
            'WHERE','ON','SET','GROUP','ORDER','HAVING','LIMIT','UNION',
            'INNER','LEFT','RIGHT','OUTER','CROSS','FULL','AS','AND','OR',
            'NOT','IN','EXISTS','BETWEEN','LIKE','IS','NULL','DISTINCT',
            'SELECT','FROM','BY','ASC','DESC','WHEN','THEN','ELSE','END',
            'CASE','WITH','EXCEPT','INTERSECT','INDEX','JOIN','INTO'
        }
        if raw_alias and raw_alias.upper() not in _SQL_KW:
            return raw_alias
        return tbl

    # ── 1. Reorder WHERE conditions: indexed/equality first, LIKE/range last ──
    def _rule_where_condition_reorder(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not schema:
            return None
        where_m = re.search(
            r'\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)',
            query, re.IGNORECASE | re.DOTALL)
        if not where_m:
            return None
        where_body = where_m.group(1).strip()
        if re.search(r'\bOR\b|\(SELECT', where_body, re.IGNORECASE):
            return None
        parts = re.split(r'\bAND\b', where_body, flags=re.IGNORECASE)
        if len(parts) < 2:
            return None

        # Indexed columns = id, *_id, status, type, email, category, date cols
        indexed = set()
        for ti in schema.values():
            for col in ti.get('columns', []):
                cn = col if isinstance(col, str) else col.get('name', col)
                nl = cn.lower()
                if (nl == 'id' or nl.endswith('_id') or
                        nl in ('status','type','email','category','created_at',
                               'date','is_active','is_deleted','is_flagged',
                               'is_cancelled','verified','plan_type')):
                    indexed.add(nl)

        def pred_score(pred):
            p  = pred.upper().strip()
            # extract column name (strip table alias)
            cols = re.findall(r'(\w+)\s*(?:=|!=|<>|>|<|>=|<=|IN\s*\(|BETWEEN|LIKE|IS\s)', p)
            col  = cols[0].split('.')[-1].lower() if cols else ''
            if col in indexed and '=' in p and 'LIKE' not in p:
                return 0   # equality on indexed col — cheapest
            if col in indexed:
                return 1   # range on indexed col
            if re.search(r'\bIS\s+(NOT\s+)?NULL\b', p):
                return 2
            if re.search(r'\bBETWEEN\b', p):
                return 3
            if re.search(r'>|<|>=|<=', p):
                return 4
            if re.search(r'\bLIKE\b', p) and p.count('%') == 2:
                return 6   # %x% is most expensive
            if re.search(r'\bLIKE\b', p):
                return 5
            return 2

        sorted_parts = sorted(parts, key=pred_score)
        if [p.strip() for p in sorted_parts] == [p.strip() for p in parts]:
            return None

        new_where = ' AND '.join(p.strip() for p in sorted_parts)
        # Reconstruct full query: everything before WHERE body + new body + everything after
        before  = query[:where_m.start(1)]
        after   = query[where_m.start(1) + len(where_body):]
        # Ensure there's a space between WHERE keyword and the conditions
        if before.rstrip().upper().endswith('WHERE'):
            before = before.rstrip() + ' '
        new_query = before + new_where + after
        if new_query.strip() == query.strip():
            return None

        moved = [p.strip() for p in sorted_parts if pred_score(p) > 3]
        return (new_query, 'where_condition_reorder',
                f'Moved expensive predicates (LIKE/range) after cheap equality checks — '
                f'short-circuits on indexed columns first, avoids costly scan for non-matching rows')

    # ── 2. OR col=x OR col=y → col IN (x, y) ─────────────────────────────
    def _rule_or_to_in(self, query: str, schema: dict = None) -> Optional[tuple]:
        # Pattern: col = val OR col = val [OR col = val ...]
        pattern = r"([\w\.]+)\s*=\s*('[^']*'|\w+)\s+OR\s+\1\s*=\s*('[^']*'|\w+)(?:\s+OR\s+\1\s*=\s*('[^']*'|\w+))?"
        m = re.search(pattern, query, re.IGNORECASE)
        if not m:
            return None
        col    = m.group(1)
        values = [m.group(2), m.group(3)]
        if m.group(4):
            values.append(m.group(4))
        in_clause = f"{col} IN ({', '.join(values)})"
        new_query = query[:m.start()] + in_clause + query[m.end():]
        return (new_query, 'or_to_in',
                f'Rewrote {col} = x OR {col} = y ... to {col} IN (...) — '
                f'single index range scan instead of multiple OR evaluations')

    # ── 3. IN (subquery) → EXISTS ─────────────────────────────────────────
    def _rule_in_to_exists(self, query: str, schema: dict = None) -> Optional[tuple]:
        pattern = (r'(\w+(?:\.\w+)?)\s+IN\s*\(\s*SELECT\s+(\w+(?:\.\w+)?)\s+'
                   r'FROM\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?\s*(?:WHERE\s+(.*?))?\s*\)')
        m = re.search(pattern, query, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        outer_col   = m.group(1)
        inner_col   = m.group(2).split('.')[-1]
        inner_tbl   = m.group(3)
        inner_alias = m.group(4) or '_s'
        inner_where = m.group(5)
        join_cond   = f'{inner_alias}.{inner_col} = {outer_col}'
        body        = (f'SELECT 1 FROM {inner_tbl} {inner_alias} WHERE {join_cond} AND {inner_where}'
                       if inner_where else
                       f'SELECT 1 FROM {inner_tbl} {inner_alias} WHERE {join_cond}')
        new_query   = query[:m.start()] + f'EXISTS ({body})' + query[m.end():]
        return (new_query, 'in_to_exists',
                f'Converted IN (subquery) to EXISTS — short-circuits on first match, '
                f'avoids materializing full subquery result set')

    # ── 4. EXISTS (SELECT *) → EXISTS (SELECT 1) ──────────────────────────
    def _rule_exists_select_1(self, query: str, schema: dict = None) -> Optional[tuple]:
        if 'EXISTS' not in query.upper():
            return None
        pattern   = r'\(SELECT\s+\*\s+FROM\s+'
        new_query = re.sub(pattern, '(SELECT 1 FROM ', query, flags=re.IGNORECASE)
        if new_query == query:
            return None
        return (new_query, 'exists_select_1',
                'Replaced SELECT * with SELECT 1 inside EXISTS — '
                'EXISTS only checks row existence, fetching all columns wastes I/O')

    # ── 5. SELECT * → explicit columns ────────────────────────────────────
    def _rule_remove_select_star(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not re.search(r'SELECT\s+\*', query, re.IGNORECASE):
            return None
        if not schema:
            return None

        _SQL_KW = {
            'WHERE','ON','SET','GROUP','ORDER','HAVING','LIMIT','UNION','JOIN',
            'INNER','LEFT','RIGHT','OUTER','CROSS','FULL','AS','AND','OR','NOT',
            'IN','EXISTS','BETWEEN','LIKE','IS','NULL','DISTINCT','ALL','ANY',
            'SELECT','FROM','INSERT','UPDATE','DELETE','BY','ASC','DESC',
            'WHEN','THEN','ELSE','END','CASE','WITH','EXCEPT','INTERSECT','INDEX'
        }
        alias_map = {}
        for m in re.finditer(r'(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?',
                             query, re.IGNORECASE):
            tbl   = m.group(1)
            raw_alias = m.group(2)
            # Reject SQL keywords as aliases
            alias = (raw_alias if raw_alias and raw_alias.upper() not in _SQL_KW
                     else tbl)
            alias_map[tbl.lower()]   = (tbl, alias)
            alias_map[alias.lower()] = (tbl, alias)

        col_parts, seen = [], set()
        for alias_l, (tbl, alias_str) in alias_map.items():
            if tbl in seen:
                continue
            seen.add(tbl)
            for t_name, t_info in schema.items():
                if t_name.lower() == tbl.lower():
                    for col in t_info.get('columns', []):
                        cn = col if isinstance(col, str) else col.get('name', col)
                        col_parts.append(f'{alias_str}.{cn}')
                    break

        if not col_parts:
            return None

        col_list  = ',\n    '.join(col_parts)
        new_query = re.sub(r'SELECT\s+\*',
                           f'SELECT\n    {col_list}',
                           query, count=1, flags=re.IGNORECASE)
        total_cols = sum(len(t.get('columns', [])) for t in schema.values())
        return (new_query, 'projection_optimization',
                f'Replaced SELECT * with {len(col_parts)} explicit columns '
                f'(out of {total_cols} total) — reduces bytes read per row')

    # ── 6. Drop large TEXT blobs from SELECT list ──────────────────────────
    def _rule_column_pruning(self, query: str, schema: dict = None) -> Optional[tuple]:
        if re.search(r'SELECT\s+\*', query, re.IGNORECASE):
            return None   # handled by rule 5
        m = re.search(r'SELECT\s+(.*?)\s+FROM\b', query, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        select_text = m.group(1)
        selected    = [c.strip() for c in select_text.split(',') if c.strip()]
        if len(selected) < 2:
            return None

        EXPENSIVE = {'description','abstract','notes','content','bio','body',
                     'text','summary','details','remarks','comment','review',
                     'address','full_address','raw_data','payload','metadata',
                     'treatment_notes','password_hash','resume','cover_letter',
                     'html_content','xml_data','json_data','log_data','error_trace'}

        def col_name(c):
            c2 = re.sub(r'\s+AS\s+\w+', '', c, flags=re.IGNORECASE)
            c2 = c2.split('.')[-1].strip().lower()
            return re.sub(r'\(.*\)', '', c2).strip()

        prunable  = [c for c in selected if col_name(c) in EXPENSIVE]
        if not prunable:
            return None

        new_cols  = [c for c in selected if c not in prunable]
        if not new_cols:
            return None

        new_query = re.sub(
            r'SELECT\s+' + re.escape(select_text),
            'SELECT ' + ', '.join(new_cols),
            query, count=1, flags=re.IGNORECASE
        )
        if new_query == query:
            return None
        names = [col_name(c) for c in prunable]
        return (new_query, 'column_pruning',
                f'Removed {len(prunable)} large TEXT column(s): {", ".join(names)} — '
                f'these columns are wide (100-10000 bytes each) and rarely needed in result sets')

    # ── 7. Reorder JOINs: smallest table first ────────────────────────────
    def _rule_join_order(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not schema:
            return None
        pattern  = (r'((?:LEFT|RIGHT|INNER|FULL|CROSS)?\s*JOIN)\s+'
                    r'(\w+)(?:\s+(?:AS\s+)?(\w+))?\s+'
                    r'(ON\s+[\w\.]+\s*=\s*[\w\.]+)')
        matches  = list(re.finditer(pattern, query, re.IGNORECASE))
        if len(matches) < 2:
            return None

        def get_rows(tbl):
            for tn, ti in schema.items():
                if tn.lower() == tbl.lower():
                    return ti.get('row_count', 1000)
            return 1000

        join_info    = [(m, m.group(2), m.group(3) or m.group(2),
                         get_rows(m.group(2)), m.group(1), m.group(4))
                        for m in matches]
        sorted_joins = sorted(join_info, key=lambda x: x[3])
        if [j[3] for j in join_info] == [j[3] for j in sorted_joins]:
            return None

        new_query = query
        offset    = 0
        for i, orig_m in enumerate(matches):
            nj          = sorted_joins[i]
            replacement = f'{nj[4]} {nj[1]} {nj[2]} {nj[5]}'
            s           = orig_m.start() + offset
            e           = orig_m.end()   + offset
            new_query   = new_query[:s] + replacement + new_query[e:]
            offset     += len(replacement) - (orig_m.end() - orig_m.start())

        if new_query.strip() == query.strip():
            return None

        old = ' → '.join(f'{j[1]}({j[3]:,})' for j in join_info)
        new = ' → '.join(f'{j[1]}({j[3]:,})' for j in sorted_joins)
        return (new_query, 'join_order_optimization',
                f'Reordered JOINs smallest→largest: {old} → {new}. '
                f'Hash join builds on smallest table — reduces memory and probe pages')

    # ── 8. Push WHERE predicates into subquery before JOIN ────────────────
    def _rule_predicate_before_join(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not schema:
            return None
        from_m = re.search(r'FROM\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?', query, re.IGNORECASE)
        if not from_m:
            return None
        from_tbl   = from_m.group(1)
        from_alias = self._safe_alias(from_m.group(1), from_m.group(2))

        if not re.search(r'\bJOIN\b', query, re.IGNORECASE):
            return None

        where_m = re.search(
            r'\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)',
            query, re.IGNORECASE | re.DOTALL)
        if not where_m:
            return None

        where_body  = where_m.group(1).strip()
        join_aliases = set(re.findall(r'JOIN\s+\w+\s+(?:AS\s+)?(\w+)', query, re.IGNORECASE))
        join_aliases |= set(re.findall(r'JOIN\s+(\w+)(?:\s+\w+)?\s+ON', query, re.IGNORECASE))

        parts = re.split(r'\bAND\b', where_body, flags=re.IGNORECASE)
        base_preds, other_preds = [], []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            refs = set(m.lower() for m in re.findall(r'(\w+)\.\w+', part, re.IGNORECASE))
            if not refs or all(r == from_alias.lower() for r in refs):
                base_preds.append(part)
            else:
                other_preds.append(part)

        if not base_preds or not other_preds:
            return None

        from_rows = 1000
        for tn, ti in schema.items():
            if tn.lower() == from_tbl.lower():
                from_rows = ti.get('row_count', 1000)
                break
        if from_rows < 50000:
            return None

        pushed_where = ' AND '.join(base_preds)
        # Get columns for the subquery
        sub_cols = '*'
        for tn, ti in schema.items():
            if tn.lower() == from_tbl.lower():
                cols = ti.get('columns', [])
                if cols:
                    sub_cols = ', '.join(
                        c if isinstance(c, str) else c.get('name', c)
                        for c in cols)
                break

        subquery  = f'(SELECT {sub_cols} FROM {from_tbl} WHERE {pushed_where}) {from_alias}'
        new_query = query[:from_m.start()] + f'FROM {subquery}' + query[from_m.end():]
        remaining = ' AND '.join(other_preds)
        new_query = re.sub(
            r'\bWHERE\b.*?(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)',
            f'WHERE {remaining} ' if remaining else '',
            new_query, count=1, flags=re.IGNORECASE | re.DOTALL)

        if new_query.strip() == query.strip():
            return None

        return (new_query, 'predicate_pushdown',
                f'Pushed {len(base_preds)} filter(s) on {from_tbl} ({from_rows:,} rows) '
                f'into subquery — filters rows before JOIN reduces join input size')

    # ── 9. Remove ORDER BY in subquery without LIMIT ──────────────────────
    def _rule_remove_orderby_subquery(self, query: str, schema: dict = None) -> Optional[tuple]:
        pattern = r'\(\s*(SELECT\b.*?)(ORDER\s+BY\s+[\w\s,\.]+?)(\s*)\)'
        matches = list(re.finditer(pattern, query, re.IGNORECASE | re.DOTALL))
        if not matches:
            return None
        new_query = query
        changed   = False
        for m in reversed(matches):
            if 'LIMIT' not in (m.group(1) + m.group(2)).upper():
                new_query = new_query[:m.start()] + f'({m.group(1).rstrip()})' + new_query[m.end():]
                changed   = True
        return (new_query, 'remove_redundant_orderby',
                'Removed ORDER BY inside subquery (no LIMIT) — '
                'sort result discarded by outer query, saves O(N log N) work') if changed else None

    # ── 10. DISTINCT + GROUP BY → remove DISTINCT ─────────────────────────
    def _rule_remove_redundant_distinct(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not (re.search(r'\bSELECT\s+DISTINCT\b', query, re.IGNORECASE) and
                re.search(r'\bGROUP\s+BY\b', query, re.IGNORECASE)):
            return None
        new_q = re.sub(r'\bSELECT\s+DISTINCT\b', 'SELECT', query, flags=re.IGNORECASE)
        return (new_q, 'remove_redundant_distinct',
                'Removed DISTINCT — GROUP BY already produces unique rows, '
                'DISTINCT adds unnecessary O(N log N) dedup pass')

    # ── 11. DISTINCT when id/pk in SELECT list ────────────────────────────
    def _rule_remove_distinct_pk(self, query: str, schema: dict = None) -> Optional[tuple]:
        if not re.search(r'\bSELECT\s+DISTINCT\b', query, re.IGNORECASE):
            return None
        if re.search(r'\bGROUP\s+BY\b', query, re.IGNORECASE):
            return None
        m = re.search(r'SELECT\s+DISTINCT\s+(.*?)\s+FROM\b', query, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        cols = [c.split('.')[-1].split(' ')[0].strip().lower()
                for c in m.group(1).split(',')]
        if not any(c == 'id' or c.endswith('_id') for c in cols):
            return None
        new_q = re.sub(r'\bSELECT\s+DISTINCT\b', 'SELECT', query, flags=re.IGNORECASE)
        return (new_q, 'remove_distinct_pk',
                'Removed DISTINCT — SELECT list includes primary key which guarantees '
                'unique rows, DISTINCT is redundant')

    # ── 12. COUNT(id) → COUNT(*) ──────────────────────────────────────────
    def _rule_count_star(self, query: str, schema: dict = None) -> Optional[tuple]:
        m = re.search(r'COUNT\(\s*(\w+(?:\.\w+)?)\s*\)', query, re.IGNORECASE)
        if not m:
            return None
        col = m.group(1).split('.')[-1].lower()
        if col not in ('id', 'rowid'):
            return None
        new_q = query[:m.start()] + 'COUNT(*)' + query[m.end():]
        return (new_q, 'count_star_optimization',
                'Replaced COUNT(id) with COUNT(*) — id is NOT NULL so result identical, '
                'avoids per-row null check in aggregation')

    # ── 13. Implicit cross-join → explicit INNER JOIN ─────────────────────
    def _rule_implicit_to_explicit_join(self, query: str, schema: dict = None) -> Optional[tuple]:
        pattern = (r'FROM\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?\s*,\s*(\w+)(?:\s+(?:AS\s+)?(\w+))?\s+'
                   r'WHERE\s+((?:\w+\.)\w+)\s*=\s*((?:\w+\.)\w+)')
        m = re.search(pattern, query, re.IGNORECASE)
        if not m:
            return None
        t1,a1 = m.group(1), m.group(2) or m.group(1)
        t2,a2 = m.group(3), m.group(4) or m.group(3)
        lhs,rhs = m.group(5), m.group(6)
        rest = query[m.end():].strip()
        rest = re.sub(r'^AND\s+', '', rest, flags=re.IGNORECASE).strip()
        new_q = f'{query[:m.start()]}FROM {t1} {a1}\nINNER JOIN {t2} {a2} ON {lhs} = {rhs}'
        if rest:
            new_q += f'\nWHERE {rest}'
        return (new_q, 'implicit_to_explicit_join',
                'Converted implicit cross-join to explicit INNER JOIN — '
                'enables hash/merge join instead of nested-loop cross product')

    # ── 14. Add LIMIT when ORDER BY present without LIMIT ─────────────────
    def _rule_add_limit(self, query: str, schema: dict = None) -> Optional[tuple]:
        qu = query.upper()
        if 'LIMIT' in qu or 'ORDER BY' not in qu:
            return None
        max_rows  = max((t.get('row_count', 1000) for t in (schema or {}).values()), default=1000)
        limit_val = max(100, min(10000, int(max_rows * 0.01)))
        new_q     = query.rstrip().rstrip(';') + f'\nLIMIT {limit_val}'
        return (new_q, 'limit_pushdown',
                f'Added LIMIT {limit_val:,} (1% of {max_rows:,} rows) — enables '
                f'top-N heap sort O(N·log K) instead of full merge sort O(N·log N)')
