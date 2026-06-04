"""
Complexity Analyzer
Computes a human-readable complexity score for a SQL query.
"""
import re
import math


COMPLEXITY_WEIGHTS = {
    'join':        10,
    'subquery':    15,
    'aggregate':    5,
    'distinct':     3,
    'order_by':     4,
    'group_by':     5,
    'having':       6,
    'union':        8,
    'like':         2,
    'or_condition': 3,
    'select_star':  5,
    'nested_depth': 8,
    'table_count':  4,
    'condition':    2,
}


class ComplexityAnalyzer:
    def analyze(self, query: str, schema: dict = None) -> dict:
        q = query.upper()
        factors = {}

        factors['join']        = len(re.findall(r'\bJOIN\b', q))
        factors['subquery']    = len(re.findall(r'\(SELECT', q))
        factors['aggregate']   = len(re.findall(r'\b(COUNT|SUM|AVG|MIN|MAX)\s*\(', q))
        factors['distinct']    = int('DISTINCT' in q)
        factors['order_by']    = int('ORDER BY' in q)
        factors['group_by']    = int('GROUP BY' in q)
        factors['having']      = int('HAVING' in q)
        factors['union']       = int('UNION' in q)
        factors['like']        = len(re.findall(r'\bLIKE\b', q))
        factors['or_condition']= len(re.findall(r'\bOR\b', q))
        factors['select_star'] = int(bool(re.search(r'SELECT\s+\*', q)))
        factors['table_count'] = len(set(re.findall(r'\bFROM\s+(\w+)', q) + re.findall(r'\bJOIN\s+(\w+)', q)))
        factors['condition']   = len(re.findall(r'\bAND\b|\bOR\b|\bWHERE\b', q))

        # Nesting depth
        depth = 0
        max_depth = 0
        for ch in query:
            if ch == '(':
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == ')':
                depth -= 1
        factors['nested_depth'] = max_depth

        raw_score = sum(factors[k] * COMPLEXITY_WEIGHTS[k] for k in factors)
        score = min(100, raw_score)

        if score < 20:
            level = 'Simple'
            color = 'green'
        elif score < 45:
            level = 'Moderate'
            color = 'yellow'
        elif score < 70:
            level = 'Complex'
            color = 'orange'
        else:
            level = 'Very Complex'
            color = 'red'

        top_factors = sorted(
            [(k, factors[k] * COMPLEXITY_WEIGHTS[k]) for k in factors if factors[k] > 0],
            key=lambda x: -x[1]
        )[:4]

        return {
            'score': round(score, 1),
            'level': level,
            'color': color,
            'raw_score': round(raw_score, 1),
            'factors': factors,
            'top_contributors': [{'factor': k, 'contribution': v} for k, v in top_factors],
        }
