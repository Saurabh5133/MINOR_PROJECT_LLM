"""
Index Advisor
Analyzes SQL queries and schemas to recommend specific CREATE INDEX statements.
Shows estimated cost WITH vs WITHOUT each index using the same cost model
as the rest of the optimizer.

How it works:
  1. Parse WHERE, JOIN ON, ORDER BY, GROUP BY columns from the query
  2. Check which of those columns are NOT already indexed
  3. For each un-indexed column, simulate what cost would be with an index
  4. Rank recommendations by estimated savings
  5. Generate specific CREATE INDEX SQL statements

Cost model:
  Without index: full table scan = rows / PAGE_ROWS pages
  With index:    index seek      = log2(rows/PAGE_ROWS) + selectivity * rows/PAGE_ROWS
"""

import re
import math
from typing import List, Dict, Optional


PAGE_ROWS = 100  # rows per 8KB page

# Already-indexed column patterns (same logic as sqlite_engine.py)
DEFAULT_INDEXED = {
    'id', 'rowid', 'email', 'status', 'type', 'category',
    'created_at', 'updated_at', 'is_active', 'is_deleted',
    'is_flagged', 'is_cancelled', 'plan_type', 'verified',
}


class IndexAdvisor:

    def analyze(self, query: str, schema: dict) -> dict:
        """
        Full index analysis for a query.
        Returns recommendations with cost estimates and CREATE INDEX statements.
        """
        schema = schema or {}

        # Build alias → table mapping
        alias_map = self._build_alias_map(query)

        # Extract column usage from different query clauses
        where_cols   = self._extract_where_cols(query)
        join_cols    = self._extract_join_cols(query)
        orderby_cols = self._extract_orderby_cols(query)
        groupby_cols = self._extract_groupby_cols(query)

        # Resolve aliases to real table names
        all_col_refs = []
        for col_ref, clause in (
            [(c, 'WHERE')    for c in where_cols]   +
            [(c, 'JOIN ON')  for c in join_cols]     +
            [(c, 'ORDER BY') for c in orderby_cols]  +
            [(c, 'GROUP BY') for c in groupby_cols]
        ):
            resolved = self._resolve_column(col_ref, alias_map, schema)
            if resolved:
                all_col_refs.append({
                    'raw':    col_ref,
                    'table':  resolved['table'],
                    'column': resolved['column'],
                    'clause': clause,
                })

        # Deduplicate (same table.column can appear in multiple clauses)
        seen       = set()
        unique_refs = []
        for ref in all_col_refs:
            key = f'{ref["table"]}.{ref["column"]}'
            if key not in seen:
                seen.add(key)
                unique_refs.append(ref)

        # Find which columns are NOT indexed
        recommendations = []
        for ref in unique_refs:
            tbl_name = ref['table']
            col_name = ref['column']

            # Skip already-indexed columns
            if self._is_already_indexed(col_name):
                continue

            # Get table info
            tbl_info = self._get_table_info(tbl_name, schema)
            if not tbl_info:
                continue

            row_count = tbl_info.get('row_count', 1000)

            # Calculate cost without index (full scan)
            cost_without = self._cost_full_scan(row_count)

            # Calculate cost with index
            selectivity = self._col_selectivity(col_name, ref['clause'], query)
            cost_with   = self._cost_index_scan(row_count, selectivity)

            savings_abs = cost_without - cost_with
            savings_pct = round(savings_abs / max(cost_without, 1) * 100, 1)

            if savings_pct < 1:
                continue  # not worth recommending

            # Determine index type
            idx_type   = self._recommend_index_type(col_name, ref['clause'], query)
            create_sql = self._generate_create_index(tbl_name, col_name, idx_type)

            recommendations.append({
                'table':         tbl_name,
                'column':        col_name,
                'clause':        ref['clause'],
                'index_type':    idx_type,
                'create_sql':    create_sql,
                'cost_without':  round(cost_without, 2),
                'cost_with':     round(cost_with, 2),
                'savings_pages': round(savings_abs, 2),
                'savings_pct':   savings_pct,
                'row_count':     row_count,
                'reason':        self._explain_reason(col_name, ref['clause'], idx_type, row_count, savings_pct),
                'priority':      self._priority(savings_pct, row_count),
            })

        # Sort by savings (highest first)
        recommendations.sort(key=lambda x: (-x['savings_pct'], -x['row_count']))

        # Overall impact summary
        total_cost_now   = self._estimate_query_cost_no_index(query, schema)
        total_cost_ideal = self._estimate_query_cost_with_indexes(query, schema, recommendations)
        overall_savings  = round((total_cost_now - total_cost_ideal) / max(total_cost_now, 1) * 100, 1)

        return {
            'recommendations':   recommendations,
            'total_count':       len(recommendations),
            'columns_analyzed':  len(unique_refs),
            'query_cost_current': round(total_cost_now, 2),
            'query_cost_ideal':   round(total_cost_ideal, 2),
            'overall_savings_pct': max(0, overall_savings),
            'summary':           self._build_summary(recommendations, overall_savings),
            'already_indexed':   [
                f'{self._resolve_column(c, alias_map, schema) or {}}' 
                for c in where_cols + join_cols
                if self._is_already_indexed(c.split('.')[-1].lower())
            ],
        }

    # ─────────────────────────────────────── parsing ──

    def _build_alias_map(self, query: str) -> dict:
        """alias_lower → real_table_name"""
        alias_map = {}
        for m in re.finditer(r'(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?',
                             query, re.IGNORECASE):
            tbl   = m.group(1)
            alias = m.group(2) or tbl
            alias_map[tbl.lower()]   = tbl
            alias_map[alias.lower()] = tbl
        return alias_map

    def _extract_where_cols(self, query: str) -> List[str]:
        where = re.search(
            r'\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)',
            query, re.IGNORECASE | re.DOTALL)
        if not where:
            return []
        clause = where.group(1)
        # Extract column references: col = val, col > val, col LIKE, col BETWEEN, col IN
        return re.findall(
            r'\b(\w+(?:\.\w+)?)\s*(?:=|!=|<>|>|<|>=|<=|LIKE|BETWEEN|IN\s*\()',
            clause, re.IGNORECASE)

    def _extract_join_cols(self, query: str) -> List[str]:
        cols = []
        for m in re.finditer(r'\bON\s+([\w\.]+)\s*=\s*([\w\.]+)', query, re.IGNORECASE):
            cols.extend([m.group(1), m.group(2)])
        return cols

    def _extract_orderby_cols(self, query: str) -> List[str]:
        m = re.search(r'\bORDER\s+BY\b(.*?)(?:\bLIMIT\b|$)', query, re.IGNORECASE | re.DOTALL)
        if not m:
            return []
        return re.findall(r'\b(\w+(?:\.\w+)?)\b(?:\s+(?:ASC|DESC))?', m.group(1), re.IGNORECASE)

    def _extract_groupby_cols(self, query: str) -> List[str]:
        m = re.search(r'\bGROUP\s+BY\b(.*?)(?:\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)',
                      query, re.IGNORECASE | re.DOTALL)
        if not m:
            return []
        return re.findall(r'\b(\w+(?:\.\w+)?)\b', m.group(1), re.IGNORECASE)

    def _resolve_column(self, col_ref: str, alias_map: dict, schema: dict) -> Optional[dict]:
        """Resolve 'alias.column' or 'column' to {'table': ..., 'column': ...}"""
        col_ref = col_ref.strip()
        if '.' in col_ref:
            parts  = col_ref.split('.')
            alias  = parts[0].lower()
            col    = parts[1].lower()
            table  = alias_map.get(alias)
            if not table:
                return None
            # Verify column exists in schema
            tbl_info = self._get_table_info(table, schema)
            if not tbl_info:
                return None
            cols = [
                (c if isinstance(c, str) else c.get('name', c)).lower()
                for c in tbl_info.get('columns', [])
            ]
            if col not in cols:
                return None
            return {'table': table, 'column': col}
        else:
            # Unqualified column — find which table has it
            col = col_ref.lower()
            for tbl_name, tbl_info in schema.items():
                cols = [
                    (c if isinstance(c, str) else c.get('name', c)).lower()
                    for c in tbl_info.get('columns', [])
                ]
                if col in cols:
                    return {'table': tbl_name, 'column': col}
            return None

    def _get_table_info(self, table_name: str, schema: dict) -> Optional[dict]:
        for tn, ti in schema.items():
            if tn.lower() == table_name.lower():
                return ti
        return None

    # ─────────────────────────────────────── index logic ──

    def _is_already_indexed(self, col_name: str) -> bool:
        n = col_name.lower()
        return (n == 'id' or
                n.endswith('_id') or
                n in DEFAULT_INDEXED)

    def _col_selectivity(self, col_name: str, clause: str, query: str) -> float:
        """Estimate selectivity of this column's predicate."""
        qu = query.upper()
        # Find the predicate for this column
        col_upper = col_name.upper()

        if clause == 'ORDER BY' or clause == 'GROUP BY':
            return 1.0  # index used for sorting, not filtering

        if re.search(rf'\b{col_upper}\s+LIKE\b', qu):
            return 0.20
        if re.search(rf'\b{col_upper}\s+BETWEEN\b', qu):
            return 0.10
        if re.search(rf'\b{col_upper}\s*(?:>|<|>=|<=)', qu):
            return 0.25
        if re.search(rf'\b{col_upper}\s+IN\s*\(', qu):
            # Count IN list values
            m = re.search(rf'\b{col_upper}\s+IN\s*\(([^)]*)\)', qu)
            if m:
                n = len([v for v in m.group(1).split(',') if v.strip()])
                return min(0.5, n * 0.05)
            return 0.10
        # Default: equality
        return 0.05

    def _cost_full_scan(self, row_count: int) -> float:
        return max(1, row_count / PAGE_ROWS)

    def _cost_index_scan(self, row_count: int, selectivity: float) -> float:
        pages = max(1, row_count / PAGE_ROWS)
        # Index seek: log2(pages) to find entry + selective range scan
        return math.log2(pages + 1) + pages * selectivity

    def _recommend_index_type(self, col_name: str, clause: str, query: str) -> str:
        qu    = query.upper()
        col_u = col_name.upper()

        if clause == 'ORDER BY':
            return 'BTREE'   # B-tree for sorting
        if clause == 'GROUP BY':
            return 'BTREE'
        if re.search(rf'\b{col_u}\s+LIKE\b', qu):
            return 'BTREE'   # LIKE with prefix can use B-tree
        if re.search(rf'\b{col_u}\s+BETWEEN\b', qu):
            return 'BTREE'   # range queries use B-tree
        if re.search(rf'\b{col_u}\s*(?:>|<)', qu):
            return 'BTREE'
        # Equality → could be hash, but B-tree is universal
        return 'BTREE'

    def _generate_create_index(self, table: str, column: str, idx_type: str) -> str:
        idx_name = f'idx_{table}_{column}'
        return f'CREATE INDEX {idx_name} ON {table} ({column});'

    def _explain_reason(self, col: str, clause: str, idx_type: str,
                        row_count: int, savings_pct: float) -> str:
        reasons = {
            'WHERE':    f'Column `{col}` is used in WHERE clause on {row_count:,} rows. '
                        f'Without index, every query scans all {row_count:,} rows. '
                        f'With B-tree index, seeks directly to matching rows.',
            'JOIN ON':  f'Column `{col}` is a JOIN key on {row_count:,} rows. '
                        f'Without index, each join probes the full table. '
                        f'With index, join uses index nested-loop or hash join.',
            'ORDER BY': f'Column `{col}` is used in ORDER BY on {row_count:,} rows. '
                        f'Without index, requires full sort O(N log N). '
                        f'With index, rows come pre-sorted — no sort needed.',
            'GROUP BY': f'Column `{col}` is used in GROUP BY on {row_count:,} rows. '
                        f'Without index, requires sort+group pass. '
                        f'With index, groups are already ordered.',
        }
        return reasons.get(clause, f'Column `{col}` used in {clause}. Index reduces scan cost by ~{savings_pct}%.')

    def _priority(self, savings_pct: float, row_count: int) -> str:
        if savings_pct >= 80 or row_count >= 1_000_000:
            return 'HIGH'
        if savings_pct >= 40 or row_count >= 100_000:
            return 'MEDIUM'
        return 'LOW'

    # ─────────────────────────────────────── overall cost ──

    def _estimate_query_cost_no_index(self, query: str, schema: dict) -> float:
        """Rough total query cost without any recommended indexes."""
        total = 0
        from_tbls = re.findall(r'(?:FROM|JOIN)\s+(\w+)', query, re.IGNORECASE)
        for tbl in from_tbls:
            for tn, ti in schema.items():
                if tn.lower() == tbl.lower():
                    total += self._cost_full_scan(ti.get('row_count', 1000))
                    break
        return max(1, total)

    def _estimate_query_cost_with_indexes(self, query: str, schema: dict,
                                           recommendations: list) -> float:
        """Rough total query cost if all recommended indexes were added."""
        # Start with no-index cost
        total = self._estimate_query_cost_no_index(query, schema)
        # Apply savings from each recommendation
        for rec in recommendations:
            tbl_cost = self._cost_full_scan(rec['row_count'])
            savings  = tbl_cost - rec['cost_with']
            total   -= savings
        return max(1, total)

    def get_query_suggestions(self, query: str, schema: dict) -> list:
        """
        Returns non-rewrite suggestions: LIMIT hint, covering index, partitioning.
        These change semantics so they are suggestions, not automatic rewrites.
        """
        import re
        suggestions = []
        qu = query.upper()

        # Suggest LIMIT if ORDER BY present without LIMIT
        if 'ORDER BY' in qu and 'LIMIT' not in qu and 'GROUP BY' not in qu:
            max_rows = max((t.get('row_count', 1000) for t in (schema or {}).values()), default=1000)
            sort_pages = max(1, max_rows / 100)
            import math
            sort_cost_full = sort_pages * math.log2(sort_pages + 1) / 4
            k = min(1000, int(max_rows * 0.01))
            k_pages = max(1, k / 100)
            sort_cost_topn = sort_pages * math.log2(k_pages + 1) / 4
            saving = round((sort_cost_full - sort_cost_topn) / sort_cost_full * 100, 1)
            suggestions.append({
                'type':        'LIMIT_HINT',
                'title':       f'Consider adding LIMIT {k:,}',
                'description': (
                    f'Your query has ORDER BY but no LIMIT. If you only need the top results, '
                    f'adding LIMIT {k:,} enables a top-N heap sort instead of a full '
                    f'O(N log N) merge sort — reducing sort cost by ~{saving}%.'
                ),
                'example':     f'... ORDER BY ... LIMIT {k}',
                'savings_pct': saving,
                'impact':      'HIGH' if saving > 30 else 'MEDIUM',
                'note':        'This changes result set size — only add if you do not need all rows.',
            })

        # Suggest covering index if SELECT has few specific columns
        select_m = re.search(r'SELECT\s+(.*?)\s+FROM\b', query, re.IGNORECASE | re.DOTALL)
        if select_m and '*' not in select_m.group(1):
            cols = [c.strip() for c in select_m.group(1).split(',') if c.strip()]
            if 2 <= len(cols) <= 5:
                suggestions.append({
                    'type':        'COVERING_INDEX',
                    'title':       'Consider a covering index',
                    'description': (
                        f'Your query selects only {len(cols)} column(s). A covering index that includes '
                        f'both the WHERE column and the SELECT columns allows the DB to satisfy the '
                        f'entire query from the index alone — no table row reads needed.'
                    ),
                    'example':     'CREATE INDEX idx_covering ON table (where_col, select_col1, select_col2);',
                    'impact':      'MEDIUM',
                    'note':        'Most effective on high-frequency queries with selective WHERE clauses.',
                })

        return suggestions

    def _build_summary(self, recs: list, overall_savings: float) -> str:
        if not recs:
            return ('All columns used in WHERE, JOIN, ORDER BY, and GROUP BY '
                    'are already indexed. No additional indexes needed.')

        high   = [r for r in recs if r['priority'] == 'HIGH']
        medium = [r for r in recs if r['priority'] == 'MEDIUM']
        low    = [r for r in recs if r['priority'] == 'LOW']

        parts = []
        if high:
            parts.append(f'{len(high)} HIGH priority index(es) — add these immediately')
        if medium:
            parts.append(f'{len(medium)} MEDIUM priority index(es) — significant improvement')
        if low:
            parts.append(f'{len(low)} LOW priority index(es) — minor improvement')

        return (f'Found {len(recs)} missing index(es). {" | ".join(parts)}. '
                f'Adding all indexes could reduce query cost by ~{max(0,overall_savings):.0f}%.')
