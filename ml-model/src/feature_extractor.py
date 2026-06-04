"""
Feature Extractor for SQL Query Optimization
Extracts numerical features from SQL queries for ML model input.
"""
import re
import math


class FeatureExtractor:
    def __init__(self):
        self.join_types = ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN', 'CROSS JOIN', 'JOIN']
        self.aggregates = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP_CONCAT']
        self.subquery_keywords = ['SELECT', 'EXISTS', 'IN (SELECT', 'ANY', 'ALL']

    def extract(self, query: str, schema: dict = None) -> dict:
        q = query.upper().strip()

        features = {
            # Query structure
            'has_select_star': int(bool(re.search(r'SELECT\s+\*', q))),
            'column_count': self._count_selected_columns(query),
            'table_count': self._count_tables(q),
            'join_count': self._count_joins(q),
            'subquery_count': self._count_subqueries(q),
            'has_where': int('WHERE' in q),
            'has_group_by': int('GROUP BY' in q),
            'has_order_by': int('ORDER BY' in q),
            'has_having': int('HAVING' in q),
            'has_limit': int('LIMIT' in q),
            'has_distinct': int('DISTINCT' in q),
            'has_union': int('UNION' in q),
            'aggregate_count': self._count_aggregates(q),
            'condition_count': self._count_conditions(q),
            'nested_depth': self._calculate_nesting_depth(q),
            'query_length': len(query),
            'token_count': len(query.split()),
            # Schema-aware features
            'total_rows': self._estimate_total_rows(schema),
            'max_table_rows': self._get_max_table_rows(schema),
            'indexed_tables': self._count_indexed_tables(schema),
            # Complexity signals
            'has_like': int('LIKE' in q),
            'has_between': int('BETWEEN' in q),
            'has_in_list': int(bool(re.search(r'\bIN\s*\((?!SELECT)', q))),
            'has_not': int(bool(re.search(r'\bNOT\b', q))),
            'has_or': int(bool(re.search(r'\bOR\b', q))),
            'has_and': int(bool(re.search(r'\bAND\b', q))),
        }
        return features

    def _count_selected_columns(self, query: str) -> int:
        m = re.search(r'SELECT\s+(.*?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
        if not m:
            return 0
        cols = m.group(1)
        if '*' in cols:
            return 999  # wildcard
        return len([c for c in cols.split(',') if c.strip()])

    def _count_tables(self, q: str) -> int:
        tables = re.findall(r'\bFROM\s+(\w+)', q)
        joins = re.findall(r'\bJOIN\s+(\w+)', q)
        return len(set(tables + joins))

    def _count_joins(self, q: str) -> int:
        return len(re.findall(r'\bJOIN\b', q))

    def _count_subqueries(self, q: str) -> int:
        return len(re.findall(r'\(SELECT', q))

    def _count_aggregates(self, q: str) -> int:
        count = 0
        for agg in self.aggregates:
            count += len(re.findall(r'\b' + agg + r'\s*\(', q))
        return count

    def _count_conditions(self, q: str) -> int:
        # Count WHERE clause conditions
        where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|HAVING|LIMIT|$)', q, re.DOTALL)
        if not where_match:
            return 0
        where_clause = where_match.group(1)
        and_count = len(re.findall(r'\bAND\b', where_clause))
        or_count = len(re.findall(r'\bOR\b', where_clause))
        return and_count + or_count + 1

    def _calculate_nesting_depth(self, q: str) -> int:
        max_depth = 0
        depth = 0
        for char in q:
            if char == '(':
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == ')':
                depth -= 1
        return max_depth

    def _estimate_total_rows(self, schema: dict) -> int:
        if not schema:
            return 1000
        total = sum(t.get('row_count', 100) for t in schema.values())
        return total

    def _get_max_table_rows(self, schema: dict) -> int:
        if not schema:
            return 1000
        return max((t.get('row_count', 100) for t in schema.values()), default=100)

    def _count_indexed_tables(self, schema: dict) -> int:
        if not schema:
            return 0
        count = 0
        for table in schema.values():
            if table.get('indexes') or table.get('primary_key'):
                count += 1
        return count

    def to_vector(self, features: dict) -> list:
        """Convert features dict to ordered list for ML model."""
        keys = sorted(features.keys())
        return [features[k] for k in keys]

    def feature_names(self) -> list:
        dummy = self.extract("SELECT * FROM t WHERE id = 1")
        return sorted(dummy.keys())
