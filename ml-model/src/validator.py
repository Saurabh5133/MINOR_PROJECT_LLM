"""
SQL Validator
Validates SQL queries for syntax issues, schema consistency,
and semantic correctness before execution.
"""
import re


class SQLValidator:
    def validate(self, query: str, schema: dict = None) -> dict:
        errors = []
        warnings = []
        q = query.strip()
        q_upper = q.upper()

        # Basic structure checks
        if not q:
            errors.append('Query is empty')
            return self._result(False, errors, warnings)

        if not any(q_upper.startswith(k) for k in ('SELECT', 'WITH')):
            errors.append('Query must start with SELECT or WITH')

        # Balanced parentheses
        depth = 0
        for ch in q:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            if depth < 0:
                errors.append('Unmatched closing parenthesis')
                break
        if depth > 0:
            errors.append(f'Unclosed parentheses: {depth} open')

        # Check for dangerous keywords
        dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'INSERT', 'UPDATE', 'EXEC', 'EXECUTE']
        for kw in dangerous:
            if re.search(r'\b' + kw + r'\b', q_upper):
                errors.append(f'Disallowed keyword: {kw}. Only SELECT queries are supported.')

        # Schema consistency
        if schema:
            schema_warnings = self._check_schema_refs(q, schema)
            warnings.extend(schema_warnings)

        # Ambiguous column warnings
        if re.search(r'SELECT\s+\*', q_upper) and len(re.findall(r'\bJOIN\b', q_upper)) > 0:
            warnings.append('SELECT * with JOINs may return ambiguous columns')

        # Missing alias on joined tables
        join_tables = re.findall(r'\bJOIN\s+(\w+)\s+(?!ON|AS|WHERE)', q, re.IGNORECASE)
        if join_tables:
            warnings.append(f'Consider adding aliases for joined tables: {", ".join(join_tables)}')

        return self._result(len(errors) == 0, errors, warnings)

    def _check_schema_refs(self, query: str, schema: dict) -> list:
        warnings = []
        tables_in_schema = {t.lower() for t in schema.keys()}
        tables_in_query = set(re.findall(r'\bFROM\s+(\w+)', query, re.IGNORECASE))
        tables_in_query |= set(re.findall(r'\bJOIN\s+(\w+)', query, re.IGNORECASE))

        for t in tables_in_query:
            if t.lower() not in tables_in_schema:
                warnings.append(f'Table "{t}" not found in provided schema')

        return warnings

    def _result(self, valid: bool, errors: list, warnings: list) -> dict:
        return {
            'valid': valid,
            'errors': errors,
            'warnings': warnings,
            'message': 'Valid' if valid else '; '.join(errors),
        }
