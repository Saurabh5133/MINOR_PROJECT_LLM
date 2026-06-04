"""
MySQL Pipeline
Full optimization using real MySQL: real EXPLAIN, real execution time,
real schema — no simulation.
"""
import time
import re
from .mysql_engine      import MySQLEngine, DEMO_DB
from .optimizer_pipeline import OptimizerPipeline
from .index_advisor     import IndexAdvisor
from .cloud_cost        import CloudCostCalculator


class MySQLPipeline:
    def __init__(self):
        self.engine      = MySQLEngine()
        self.optimizer   = OptimizerPipeline()
        self.idx_advisor = IndexAdvisor()
        self.cloud_calc  = CloudCostCalculator()
        self.current_db  = None

    def connect(self, host, port, user, password) -> dict:
        return self.engine.connect(host, port, user, password)

    def setup_demo(self) -> dict:
        result = self.engine.setup_demo_database()
        if result.get('success'):
            self.current_db = DEMO_DB
        return result

    def use_database(self, database: str) -> dict:
        schema = self.engine.read_schema(database)
        self.current_db = database
        return {'success': True, 'schema': schema, 'tables': list(schema.keys())}

    def run(self, query: str, database: str = None,
            use_llm: bool = False) -> dict:
        t0  = time.time()
        db  = database or self.current_db or DEMO_DB

        # ── Read real schema ──────────────────────────────────────
        schema = self.engine.read_schema(db)
        if not schema:
            return {'error': f'Cannot read schema from database: {db}'}

        # ── Real EXPLAIN before ───────────────────────────────────
        plan_before = self.engine.get_execution_plan(query, db)

        # ── Real execution time before ────────────────────────────
        time_before = self.engine.get_execution_time(query, db)

        # ── Run rule optimizer + ML (uses same logic as before) ───
        opt_result = self.optimizer.run(
            query=query,
            schema=schema,
            use_llm=use_llm,
            calculate_cloud_cost=True,
        )

        optimized_query = opt_result['optimized_query']

        # ── Real EXPLAIN after ────────────────────────────────────
        plan_after = self.engine.get_execution_plan(optimized_query, db)

        # ── Real execution time after ─────────────────────────────
        time_after = self.engine.get_execution_time(optimized_query, db)

        # ── Index analysis ────────────────────────────────────────
        index_analysis = self.idx_advisor.analyze(query, schema)
        index_analysis['query_suggestions'] = \
            self.idx_advisor.get_query_suggestions(query, schema)

        # ── Compute real improvement ──────────────────────────────
        ms_before = time_before.get('elapsed_ms', 0)
        ms_after  = time_after.get('elapsed_ms', 0)
        time_improvement = 0.0
        if ms_before > 0 and ms_after < ms_before:
            time_improvement = round((ms_before - ms_after) / ms_before * 100, 1)

        return {
            **opt_result,
            'mode':               'mysql_real',
            'database':           db,
            'execution_plan_before': self._format_plan(plan_before),
            'execution_plan_after':  self._format_plan(plan_after),
            'real_time_before_ms':   ms_before,
            'real_time_after_ms':    ms_after,
            'time_improvement_pct':  time_improvement,
            'index_analysis':        index_analysis,
            'elapsed_seconds':       round(time.time() - t0, 3),
            'schema_source':         'mysql_real',
        }

    def _format_plan(self, plan: dict) -> dict:
        """Format MySQL EXPLAIN into same structure as SQLite plan."""
        if plan.get('error'):
            return plan
        steps = []
        for s in plan.get('steps', []):
            steps.append({
                'detail':      s.get('detail', ''),
                'type':        s.get('type', 'SCAN'),
                'uses_index':  s.get('uses_index', False),
                'step_cost':   s.get('step_cost', 0),
                'table':       s.get('table', ''),
                'access_type': s.get('access_type', 'ALL'),
                'key':         s.get('key'),
                'rows_est':    s.get('rows_est', 0),
                'filtered_pct':s.get('filtered_pct', 100),
                'extra':       s.get('extra', ''),
            })
        return {
            'steps': steps,
            'cost':  plan.get('cost', 0),
            'type':  'mysql_explain',
        }

    def drop_demo(self) -> dict:
        return self.engine.drop_demo_database()

    def close(self):
        self.engine.close()
