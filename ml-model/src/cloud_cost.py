"""
Cloud Cost Calculator
Translates page-I/O cost units → real dollar estimates for 3 platforms.

Real pricing (2024 on-demand):
  AWS Redshift  : dc2.large $0.25/node-hr + Spectrum $5/TB scanned
  GCP BigQuery  : on-demand $6.25/TB scanned (logical bytes, pre-compression)
  Azure Synapse : DW100c $1.20/hr + external scan $0.10/GB

Key correction vs previous version:
  rows_scanned is derived from schema row counts + selectivity estimate,
  NOT from page_io_cost (which is a cost unit, not a row count).
"""
import re
import math

PAGE_BYTES    = 8192   # 8 KB standard DB page
ROWS_PER_PAGE = 100    # ~80-100 rows per 8KB page (mixed schema)
AVG_ROW_BYTES = PAGE_BYTES / ROWS_PER_PAGE  # ~82 bytes/row

PRICING = {
    'aws_redshift': {
        'name':                'AWS Redshift',
        'logo':                'aws',
        'color':               '#FF9900',
        'node_cost_per_hr':    0.25,
        'spectrum_per_tb':     5.00,
        'compression_ratio':   0.25,   # columnar ~75% compression
        'throughput_mb_s':     300,
        'pricing_model':       'Compute ($0.25/node-hr) + Spectrum scan ($5/TB)',
        'assumptions':         'dc2.large node, 75% columnar compression, on-demand',
    },
    'gcp_bigquery': {
        'name':                'GCP BigQuery',
        'logo':                'gcp',
        'color':               '#4285F4',
        'on_demand_per_tb':    6.25,
        'slot_cost_per_hr':    0.04,
        'compression_ratio':   0.15,   # Dremel ~85% compression
        'throughput_mb_s':     2000,
        'pricing_model':       'On-demand scan ($6.25/TB)',
        'assumptions':         'On-demand pricing, Dremel engine, 85% columnar compression',
    },
    'azure_synapse': {
        'name':                'Azure Synapse',
        'logo':                'azure',
        'color':               '#0078D4',
        'dw_cost_per_hr':      1.20,
        'external_scan_per_gb': 0.10,
        'compression_ratio':   0.30,   # ~70% compression
        'throughput_mb_s':     150,
        'pricing_model':       'Compute ($1.20/hr DW100c) + external scan ($0.10/GB)',
        'assumptions':         'DW100c, 70% compression, distributed MPP',
    },
}


class CloudCostCalculator:

    def calculate_all(self, query: str, schema: dict, page_io_cost: float) -> dict:
        metrics = self._derive_metrics(query, schema, page_io_cost)
        return {
            'aws_redshift':  self._calc_aws(metrics),
            'gcp_bigquery':  self._calc_gcp(metrics),
            'azure_synapse': self._calc_azure(metrics),
            'metrics':       metrics,
        }

    def _derive_metrics(self, query: str, schema: dict, page_io_cost: float) -> dict:
        q = query.upper()

        # ── 1. Total rows across all tables referenced in query ──────────
        total_rows = sum(t.get('row_count', 1000) for t in (schema or {}).values())
        total_rows = max(1, total_rows)

        # ── 2. Identify tables actually used in this query ───────────────
        from_tables = re.findall(r'\bFROM\s+(\w+)', query, re.IGNORECASE)
        join_tables = re.findall(r'\bJOIN\s+(\w+)', query, re.IGNORECASE)
        used_table_names = set(t.lower() for t in from_tables + join_tables)

        rows_in_query = 0
        for t_name, t_info in (schema or {}).items():
            if t_name.lower() in used_table_names or not used_table_names:
                rows_in_query += t_info.get('row_count', 1000)
        rows_in_query = max(1, rows_in_query)

        # ── 3. Selectivity estimate ──────────────────────────────────────
        # Based on WHERE clause predicate types (standard DB statistics heuristics)
        selectivity = self._estimate_selectivity(query)

        # ── 4. Rows actually scanned (post-filter estimate) ───────────────
        # Full scan × selectivity for each table
        rows_scanned = rows_in_query  # base: all rows touched
        rows_returned = max(1, round(rows_in_query * selectivity))

        # ── 5. Data volume ───────────────────────────────────────────────
        # Average row width = (column count × ~20 bytes per column)
        total_cols = sum(len(t.get('columns', [])) for t in (schema or {}).values())
        avg_cols   = total_cols / max(1, len(schema or {}))
        avg_row_bytes = max(50, avg_cols * 20)  # ~20 bytes/col compressed

        bytes_scanned = rows_scanned * avg_row_bytes
        gb_scanned    = bytes_scanned / (1024 ** 3)
        tb_scanned    = gb_scanned / 1024

        # ── 6. Wall-clock time ────────────────────────────────────────────
        # page_io_cost pages × 0.1ms/page (SSD sequential read)
        # Minimum 50ms for query overhead
        estimated_sec = max(0.05, page_io_cost * 0.0001)

        # ── 7. Query complexity ───────────────────────────────────────────
        join_count = len(re.findall(r'\bJOIN\b', q))
        has_agg    = bool(re.search(r'\bCOUNT\b|\bSUM\b|\bAVG\b|\bMIN\b|\bMAX\b', q))
        has_order  = 'ORDER BY' in q
        has_where  = 'WHERE' in q

        cpu_factor = 1.0
        cpu_factor += join_count * 0.25
        cpu_factor += 0.15 if has_agg   else 0
        cpu_factor += 0.10 if has_order else 0

        return {
            'page_io_cost':   round(page_io_cost, 2),
            'total_rows':     total_rows,
            'rows_in_query':  rows_in_query,
            'rows_scanned':   rows_scanned,
            'rows_returned':  rows_returned,
            'bytes_scanned':  round(bytes_scanned, 0),
            'gb_scanned':     round(gb_scanned, 6),
            'tb_scanned':     round(tb_scanned, 9),
            'estimated_sec':  round(estimated_sec, 4),
            'selectivity':    round(selectivity, 4),
            'join_count':     join_count,
            'has_aggregate':  has_agg,
            'has_order_by':   has_order,
            'cpu_factor':     round(cpu_factor, 3),
            'avg_row_bytes':  round(avg_row_bytes, 1),
        }

    def _estimate_selectivity(self, query: str) -> float:
        """
        Estimate fraction of rows matching WHERE clause.
        Standard histogram heuristics used by most DB optimizers:
          equality (=):          ~5%  of rows
          range (>, <, BETWEEN): ~25% of rows
          LIKE '%...':           ~30% of rows
          IN (list):             ~10% per value, capped
          Multiple ANDs:         multiplicative
          OR:                    additive (capped at 1.0)
          No WHERE:              100% (full scan)
        """
        q = query.upper()
        where = re.search(r'WHERE\s+(.*?)(?:GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|$)', q, re.DOTALL)
        if not where:
            return 1.0

        clause = where.group(1)
        sel = 1.0

        eq_count    = len(re.findall(r'\w+\s*=\s*[^\s=]', clause))
        range_count = len(re.findall(r'\w+\s*(?:>|<|>=|<=|BETWEEN)\s*', clause))
        like_count  = len(re.findall(r'\bLIKE\b', clause))
        in_count    = len(re.findall(r'\bIN\s*\(', clause))
        or_count    = len(re.findall(r'\bOR\b', clause))
        null_count  = len(re.findall(r'\bIS\s+(?:NOT\s+)?NULL\b', clause))

        for _ in range(eq_count):    sel *= 0.05
        for _ in range(range_count): sel *= 0.25
        for _ in range(like_count):  sel *= 0.30
        for _ in range(in_count):    sel *= 0.10
        for _ in range(null_count):  sel *= 0.50  # IS NULL typically ~50%

        if or_count > 0:
            sel = min(1.0, sel * (1 + or_count * 0.8))

        return round(max(0.001, min(1.0, sel)), 6)

    # ─────────────────────────────────────────────────────────────────────
    def _calc_aws(self, m: dict) -> dict:
        p = PRICING['aws_redshift']

        # Spectrum charges on compressed bytes scanned, minimum 10MB per query
        compressed_gb = m['gb_scanned'] * p['compression_ratio']
        compressed_tb = compressed_gb / 1024
        min_tb = 10 / (1024 * 1024)   # 10 MB minimum
        scan_tb = max(compressed_tb, min_tb)
        scan_cost = scan_tb * p['spectrum_per_tb']

        # Compute: node-hours × rate × CPU complexity
        hours = m['estimated_sec'] / 3600
        compute_cost = hours * p['node_cost_per_hr'] * m['cpu_factor']

        # Internal data transfer (minimal, same-AZ)
        io_cost = compressed_gb * 0.001

        total = scan_cost + compute_cost + io_cost
        return {
            'platform':           p['name'],
            'logo':               p['logo'],
            'color':              p['color'],
            'total_cost_usd':     round(total, 6),
            'total_cost_display': self._fmt(total),
            'breakdown': {
                'spectrum_scan':  round(scan_cost, 6),
                'compute':        round(compute_cost, 6),
                'data_transfer':  round(io_cost, 6),
            },
            'data_scanned_gb':    round(m['gb_scanned'], 4),
            'compressed_gb':      round(compressed_gb, 6),
            'estimated_time_sec': m['estimated_sec'],
            'pricing_model':      p['pricing_model'],
            'assumptions':        p['assumptions'],
        }

    def _calc_gcp(self, m: dict) -> dict:
        p = PRICING['gcp_bigquery']

        # BQ charges on LOGICAL (uncompressed) bytes — pre-compression amount
        # Minimum 10 MB per query
        min_tb = 10 / (1024 * 1024)
        logical_tb = max(m['tb_scanned'], min_tb)
        scan_cost = logical_tb * p['on_demand_per_tb']

        # Slot usage (parallel workers)
        slots = max(10, m['cpu_factor'] * 20)
        slot_cost = (m['estimated_sec'] / 3600) * slots * p['slot_cost_per_hr']

        total = scan_cost + slot_cost
        return {
            'platform':           p['name'],
            'logo':               p['logo'],
            'color':              p['color'],
            'total_cost_usd':     round(total, 6),
            'total_cost_display': self._fmt(total),
            'breakdown': {
                'data_scan':      round(scan_cost, 6),
                'slot_usage':     round(slot_cost, 6),
            },
            'data_scanned_gb':    round(m['gb_scanned'], 4),
            'estimated_time_sec': m['estimated_sec'],
            'pricing_model':      p['pricing_model'],
            'assumptions':        p['assumptions'],
            'note':               'First 1TB/month free on BQ on-demand',
        }

    def _calc_azure(self, m: dict) -> dict:
        p = PRICING['azure_synapse']

        compressed_gb = m['gb_scanned'] * p['compression_ratio']

        # External scan
        scan_cost = max(compressed_gb, 0.00001) * p['external_scan_per_gb']

        # DW compute
        hours = m['estimated_sec'] / 3600
        compute_cost = hours * p['dw_cost_per_hr'] * m['cpu_factor']

        # Data movement (shuffle cost for distributed joins)
        movement_cost = compressed_gb * m['join_count'] * 0.02 if m['join_count'] > 0 else 0

        total = scan_cost + compute_cost + movement_cost
        return {
            'platform':           p['name'],
            'logo':               p['logo'],
            'color':              p['color'],
            'total_cost_usd':     round(total, 6),
            'total_cost_display': self._fmt(total),
            'breakdown': {
                'compute_dw':     round(compute_cost, 6),
                'external_scan':  round(scan_cost, 6),
                'data_movement':  round(movement_cost, 6),
            },
            'data_scanned_gb':    round(m['gb_scanned'], 4),
            'compressed_gb':      round(compressed_gb, 6),
            'estimated_time_sec': m['estimated_sec'],
            'pricing_model':      p['pricing_model'],
            'assumptions':        p['assumptions'],
        }

    def compare_costs(self, before: dict, after: dict) -> dict:
        result = {}
        for key in ('aws_redshift', 'gcp_bigquery', 'azure_synapse'):
            b = before.get(key, {}).get('total_cost_usd', 0)
            a = after.get(key,  {}).get('total_cost_usd', 0)
            saved = b - a
            pct   = (saved / b * 100) if b > 0 else 0
            result[key] = {
                'original_cost':   self._fmt(b),
                'optimized_cost':  self._fmt(a),
                'savings':         self._fmt(max(0, saved)),
                'savings_percent': round(pct, 1),
                'improved':        saved > 0.000001,
            }
        return result

    def _fmt(self, cost: float) -> str:
        if cost == 0:        return '$0.00'
        if cost < 0.00001:   return '< $0.00001'
        if cost < 0.001:     return f'${cost:.6f}'
        if cost < 0.01:      return f'${cost:.5f}'
        if cost < 1.0:       return f'${cost:.4f}'
        if cost < 1000:      return f'${cost:.3f}'
        return f'${cost:,.2f}'
