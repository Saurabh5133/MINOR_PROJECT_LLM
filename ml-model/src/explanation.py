"""
Explanation Generator
Produces human-readable explanations of optimization decisions.
"""


class ExplanationGenerator:
    RULE_EXPLANATIONS = {
        'projection_optimization': {
            'title': 'Projection Optimization (SELECT *)',
            'what': 'Replaced SELECT * with explicit column names.',
            'why': 'SELECT * forces the database to read ALL columns from every row, even those unused by the application. With explicit columns, the query planner can use covering indexes and skip full row reads.',
            'impact': 'Reduces I/O, improves cache efficiency, enables covering index usage.',
        },
        'predicate_pushdown': {
            'title': 'Predicate Pushdown',
            'what': 'Moved WHERE filter conditions closer to the base table scan.',
            'why': 'Filtering early (at the table level) reduces the number of rows that need to be processed in joins and aggregations, shrinking intermediate result sets dramatically.',
            'impact': 'Fewer rows participate in joins → lower memory usage and faster execution.',
        },
        'remove_redundant_orderby': {
            'title': 'Redundant ORDER BY Removal',
            'what': 'Removed ORDER BY from a subquery that did not have a LIMIT clause.',
            'why': 'Sorting inside a subquery without LIMIT is discarded by the outer query — the database still pays the full sort cost even though it has no effect on results.',
            'impact': 'Eliminates an unnecessary O(n log n) sort operation.',
        },
        'limit_injection': {
            'title': 'LIMIT Clause Addition',
            'what': 'Added a LIMIT clause to cap the maximum rows returned.',
            'why': 'Without LIMIT, the database must materialize the entire result set. With LIMIT, it can stop early once enough rows are found, especially effective with ORDER BY.',
            'impact': 'Enables early query termination, drastically reducing rows processed.',
        },
        'in_to_exists': {
            'title': 'IN to EXISTS Conversion',
            'what': 'Converted IN (SELECT ...) to EXISTS (SELECT 1 ...).',
            'why': 'EXISTS short-circuits as soon as a matching row is found, while IN must materialize the full subquery result set before comparing. EXISTS also enables better index use on the correlation column.',
            'impact': 'Faster for large subquery result sets; enables short-circuit evaluation.',
        },
        'count_optimization': {
            'title': 'COUNT(*) Optimization',
            'what': 'Replaced COUNT(column) with COUNT(*).',
            'why': 'COUNT(column) must check each value for NULL before counting. COUNT(*) counts all rows without NULL checks. For non-nullable columns (like primary keys), the result is identical but COUNT(*) is faster.',
            'impact': 'Eliminates per-row NULL check overhead in aggregate computation.',
        },
        'remove_redundant_distinct': {
            'title': 'Redundant DISTINCT Removal',
            'what': 'Removed DISTINCT because GROUP BY already produces unique rows.',
            'why': 'GROUP BY guarantees one row per group, making DISTINCT redundant. Adding DISTINCT on top forces an extra deduplication pass over already-unique data.',
            'impact': 'Removes an unnecessary O(n log n) deduplication pass.',
        },
        'implicit_to_explicit_join': {
            'title': 'Implicit to Explicit JOIN',
            'what': 'Rewrote implicit cross-join (FROM t1, t2 WHERE ...) to explicit INNER JOIN ... ON.',
            'why': 'Explicit JOIN syntax gives the query optimizer clearer intent. With implicit joins, some optimizers treat the query as a cross product and filter afterward. Explicit JOIN lets the optimizer choose the best join algorithm (hash join, merge join, nested loop) directly.',
            'impact': 'Enables better join ordering and algorithm selection by the optimizer.',
        },
        'llm_rewrite': {
            'title': 'AI-Powered Rewrite',
            'what': 'Query was rewritten by an LLM with awareness of schema and execution patterns.',
            'why': 'Large language models can apply multiple optimization patterns simultaneously and reason about query semantics in ways that rule-based systems cannot.',
            'impact': 'May combine multiple optimizations and apply context-specific rewrites.',
        },
        'original': {
            'title': 'No Optimization Applied',
            'what': 'The original query was selected as the best candidate.',
            'why': 'None of the applied optimization rules produced a query with lower estimated execution cost. The query may already be well-optimized, or the schema is too small for differences to be meaningful.',
            'impact': 'No change.',
        },
    }

    def explain(self, rule: str, cost_before: float, cost_after: float, features: dict = None) -> dict:
        info = self.RULE_EXPLANATIONS.get(rule, self.RULE_EXPLANATIONS['original'])
        improvement = round((cost_before - cost_after) / cost_before * 100, 1) if cost_before > 0 else 0

        feature_notes = []
        if features:
            if features.get('has_select_star'):
                feature_notes.append('Query uses SELECT * — projection optimization beneficial')
            if features.get('join_count', 0) > 1:
                feature_notes.append(f'Multiple JOINs ({features["join_count"]}) — join ordering matters')
            if features.get('subquery_count', 0) > 0:
                feature_notes.append('Subqueries detected — flattening or EXISTS conversion may help')
            if features.get('total_rows', 0) > 10000:
                feature_notes.append(f'Large dataset ({features["total_rows"]:,} rows) — indexes are critical')

        return {
            'rule': rule,
            'title': info['title'],
            'what_changed': info['what'],
            'why_it_helps': info['why'],
            'expected_impact': info['impact'],
            'cost_improvement_percent': improvement,
            'feature_notes': feature_notes,
        }
