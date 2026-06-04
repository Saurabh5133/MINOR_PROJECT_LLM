import React from 'react'

const PLATFORMS = {
  aws_redshift:  { short: 'AWS', cls: 'aws',   name: 'AWS Redshift'   },
  gcp_bigquery:  { short: 'GCP', cls: 'gcp',   name: 'GCP BigQuery'   },
  azure_synapse: { short: 'AZ',  cls: 'azure', name: 'Azure Synapse'  },
}

export default function CloudCostPanel({ cloudCosts }) {
  const before  = cloudCosts?.before  || {}
  const after   = cloudCosts?.after   || {}
  const comp    = cloudCosts?.comparison || {}
  const metrics = before?.metrics || {}

  return (
    <div className="animate-fade">
      <div className="section-title" style={{ marginBottom: 16 }}>Cloud Platform Cost Analysis</div>

      <div className="cloud-grid">
        {Object.entries(PLATFORMS).map(([key, p]) => {
          const b = before[key] || {}
          const a = after[key]  || {}
          const c = comp[key]   || {}
          const improved = c.improved && parseFloat(c.savings_percent) > 0

          return (
            <div className="cloud-card" key={key}>
              <div className="cloud-card-header">
                <div className={`cloud-logo ${p.cls}`}>{p.short}</div>
                <div>
                  <div className="cloud-name">{p.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{b.pricing_model}</div>
                </div>
              </div>

              <div className="cloud-card-body">
                <div className="cloud-cost-main">
                  {improved
                    ? <div className="cloud-cost-before">Before: {b.total_cost_display}</div>
                    : <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Estimated cost</div>
                  }
                  <div className="cloud-cost-after">{a.total_cost_display || b.total_cost_display || '—'}</div>
                  {improved && (
                    <div className="cloud-savings">
                      ↓ {c.savings_percent}% saved · {c.savings}
                    </div>
                  )}
                </div>

                <div className="cloud-breakdown">
                  {Object.entries(a.breakdown || b.breakdown || {}).map(([k, v]) => (
                    <div className="breakdown-row" key={k}>
                      <span>{k.replace(/_/g, ' ')}</span>
                      <strong>${typeof v === 'number' ? v.toFixed(5) : v}</strong>
                    </div>
                  ))}
                  <div className="breakdown-row">
                    <span>data scanned</span>
                    <strong>{((a.data_scanned_gb ?? b.data_scanned_gb) || 0).toFixed(4)} GB</strong>
                  </div>
                  <div className="breakdown-row">
                    <span>est. query time</span>
                    <strong>{((a.estimated_time_sec ?? b.estimated_time_sec) || 0).toFixed(3)}s</strong>
                  </div>
                </div>

                {b.assumptions && (
                  <div className="cloud-model">{b.assumptions}</div>
                )}
                {b.note && (
                  <div style={{ fontSize: 10, color: 'var(--accent)', marginTop: 6 }}>ℹ {b.note}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Query Metrics */}
      {Object.keys(metrics).length > 0 && (
        <div className="cloud-metrics">
          <div className="section-title">Query Metrics Used for Cost Calculation</div>
          <div className="metrics-grid">
            {[
              ['Total Rows',     metrics.total_rows?.toLocaleString()],
              ['Rows Scanned',   metrics.rows_scanned?.toLocaleString()],
              ['Rows Returned',  metrics.rows_returned?.toLocaleString()],
              ['Data Scanned',   `${(metrics.gb_scanned || 0).toFixed(4)} GB`],
              ['Selectivity',    `${((metrics.selectivity || 0) * 100).toFixed(2)}%`],
              ['Est. Runtime',   `${(metrics.estimated_sec || 0).toFixed(3)}s`],
              ['Joins',          metrics.join_count],
              ['CPU Factor',     `${(metrics.cpu_factor || 0).toFixed(2)}×`],
            ].map(([label, val]) => (
              <div className="metric-item" key={label}>
                <div className="metric-value">{val ?? '—'}</div>
                <div className="metric-label">{label}</div>
              </div>
            ))}
          </div>

          <div style={{
            marginTop: 16, padding: '12px 16px', background: 'var(--bg-3)',
            borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7
          }}>
            <strong style={{ color: 'var(--text-secondary)' }}>How costs are calculated:</strong>
            <br />
            Rows scanned × avg row width = bytes scanned. Then apply platform compression ratios
            and pricing formulas. <strong style={{ color: 'var(--text-secondary)' }}>AWS</strong> charges per
            TB scanned (Spectrum) + compute time. <strong style={{ color: 'var(--text-secondary)' }}>GCP</strong> charges
            per TB of logical data scanned (on-demand). <strong style={{ color: 'var(--text-secondary)' }}>Azure</strong> charges
            DW compute units + external scan. All prices are 2024 on-demand rates.
          </div>
        </div>
      )}
    </div>
  )
}
