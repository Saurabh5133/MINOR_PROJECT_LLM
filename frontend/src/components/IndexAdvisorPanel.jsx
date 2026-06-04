import React, { useState } from 'react'

const PRIORITY_CONFIG = {
  HIGH:   { color: '#ff4757', bg: 'rgba(255,71,87,0.12)',  icon: '🔴', label: 'HIGH'   },
  MEDIUM: { color: '#ffa040', bg: 'rgba(255,160,64,0.12)', icon: '🟡', label: 'MEDIUM' },
  LOW:    { color: '#00e676', bg: 'rgba(0,230,118,0.12)',  icon: '🟢', label: 'LOW'    },
}

export default function IndexAdvisorPanel({ indexAnalysis }) {
  const [copied,   setCopied]   = useState(null)
  const [expanded, setExpanded] = useState({})

  if (!indexAnalysis) return null

  const recs  = indexAnalysis.recommendations  || []
  const suggs = indexAnalysis.query_suggestions || []
  const high   = recs.filter(r => r.priority === 'HIGH')
  const medium = recs.filter(r => r.priority === 'MEDIUM')
  const low    = recs.filter(r => r.priority === 'LOW')

  const copy = (text, key) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key)
      setTimeout(() => setCopied(null), 2000)
    })
  }

  const copyAll = () => {
    const sql = recs.map(r => r.create_sql).join('\n')
    copy(sql, 'all')
  }

  const toggle = idx => setExpanded(p => ({ ...p, [idx]: !p[idx] }))

  return (
    <div className="animate-fade" style={{ display:'flex', flexDirection:'column', gap:20 }}>

      {/* ── Summary banner ── */}
      <div className="index-summary-banner">
        <div className="index-summary-left">
          <div className="index-summary-icon">⚡</div>
          <div>
            <div className="index-summary-title">
              {recs.length === 0
                ? 'All queried columns are already indexed'
                : `${recs.length} Missing Index${recs.length > 1 ? 'es' : ''} Found`}
            </div>
            <div className="index-summary-sub">{indexAnalysis.summary}</div>
          </div>
        </div>
        {recs.length > 0 && (
          <div className="index-cost-compare">
            <div className="index-cost-item">
              <div className="index-cost-label">Current Cost</div>
              <div className="index-cost-val red">{indexAnalysis.query_cost_current?.toLocaleString()}</div>
              <div className="index-cost-unit">page I/O units</div>
            </div>
            <div style={{ fontSize:20, color:'var(--text-muted)', alignSelf:'center' }}>→</div>
            <div className="index-cost-item">
              <div className="index-cost-label">With All Indexes</div>
              <div className="index-cost-val green">{indexAnalysis.query_cost_ideal?.toLocaleString()}</div>
              <div className="index-cost-unit">page I/O units</div>
            </div>
            <div className="index-savings-badge">↓{indexAnalysis.overall_savings_pct}%</div>
          </div>
        )}
      </div>

      {/* ── Priority chips + copy all ── */}
      {recs.length > 0 && (
        <div className="index-priority-row">
          {[['HIGH', high], ['MEDIUM', medium], ['LOW', low]].map(([label, items]) =>
            items.length > 0 && (
              <div key={label} className="index-priority-chip"
                style={{ background: PRIORITY_CONFIG[label].bg, border:`1px solid ${PRIORITY_CONFIG[label].color}40` }}>
                <span>{PRIORITY_CONFIG[label].icon}</span>
                <span style={{ color:PRIORITY_CONFIG[label].color, fontWeight:700 }}>{items.length}</span>
                <span style={{ color:'var(--text-muted)', fontSize:11 }}>{label}</span>
              </div>
            )
          )}
          <button className="copy-all-btn" onClick={copyAll}>
            {copied === 'all' ? '✓ Copied!' : '⎘ Copy All SQL'}
          </button>
        </div>
      )}

      {/* ── Index recommendation cards ── */}
      {recs.length === 0 ? (
        <div className="index-empty">
          <div style={{ fontSize:32, marginBottom:10 }}>✅</div>
          <div style={{ fontSize:15, fontWeight:600, color:'var(--text-primary)', marginBottom:6 }}>
            No missing indexes
          </div>
          <div style={{ fontSize:13, color:'var(--text-muted)' }}>
            All columns in WHERE, JOIN ON, ORDER BY and GROUP BY are already indexed.
          </div>
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {recs.map((rec, idx) => {
            const cfg = PRIORITY_CONFIG[rec.priority]
            const isEx = expanded[idx]
            return (
              <div key={idx} className="index-card" style={{ borderLeft:`3px solid ${cfg.color}` }}>

                {/* Header */}
                <div className="index-card-header">
                  <div className="index-card-left">
                    <span className="index-priority-badge" style={{ background:cfg.bg, color:cfg.color }}>
                      {cfg.icon} {cfg.label}
                    </span>
                    <span className="index-name">idx_{rec.table}_{rec.column}</span>
                  </div>
                  <div className="index-card-right">
                    <span className="index-clause-tag">{rec.clause}</span>
                    <span className="index-savings-pct" style={{ color:cfg.color }}>↓{rec.savings_pct}%</span>
                  </div>
                </div>

                {/* Cost bars */}
                <div className="index-cost-bar-row">
                  <div className="index-cost-bar-label">Without index</div>
                  <div className="index-cost-bar-track">
                    <div className="index-cost-bar-fill without" style={{ width:'100%' }} />
                    <span className="index-cost-bar-val">{rec.cost_without?.toLocaleString()} pages</span>
                  </div>
                </div>
                <div className="index-cost-bar-row">
                  <div className="index-cost-bar-label">With index</div>
                  <div className="index-cost-bar-track">
                    <div className="index-cost-bar-fill with"
                      style={{ width:`${Math.max(2, 100 - rec.savings_pct)}%` }} />
                    <span className="index-cost-bar-val">{rec.cost_with?.toLocaleString()} pages</span>
                  </div>
                </div>

                {/* SQL block */}
                <div className="index-sql-block">
                  <code className="index-sql-code">{rec.create_sql}</code>
                  <button className="index-copy-btn" onClick={() => copy(rec.create_sql, idx)}>
                    {copied === idx ? '✓' : '⎘'}
                  </button>
                </div>

                {/* Expand */}
                <button className="index-expand-btn" onClick={() => toggle(idx)}>
                  {isEx ? '▲ Hide details' : '▼ Why this index?'}
                </button>
                {isEx && (
                  <div className="index-detail animate-fade">
                    {[
                      ['Table',      rec.table],
                      ['Column',     rec.column],
                      ['Row count',  rec.row_count?.toLocaleString()],
                      ['Index type', rec.index_type],
                      ['Used in',    rec.clause],
                    ].map(([label, val]) => (
                      <div className="index-detail-row" key={label}>
                        <span className="index-detail-label">{label}</span>
                        <span className="index-detail-val">{val}</span>
                      </div>
                    ))}
                    <div className="index-reason">{rec.reason}</div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Query-level suggestions (LIMIT hint, covering index) ── */}
      {suggs.length > 0 && (
        <div>
          <div className="section-title" style={{ marginBottom:10 }}>
            💡 Query-Level Suggestions
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {suggs.map((s, i) => (
              <div key={i} className="suggestion-card"
                style={{ borderLeft:`3px solid ${s.impact === 'HIGH' ? 'var(--orange)' : 'var(--accent)'}` }}>
                <div className="suggestion-header">
                  <span className="suggestion-badge"
                    style={{
                      background: s.impact === 'HIGH' ? 'rgba(255,160,64,0.15)' : 'rgba(0,212,255,0.1)',
                      color:      s.impact === 'HIGH' ? 'var(--orange)' : 'var(--accent)',
                    }}>
                    {s.impact === 'HIGH' ? '⚡ HIGH IMPACT' : '📌 SUGGESTION'}
                  </span>
                  <span className="suggestion-title">{s.title}</span>
                  {s.savings_pct && (
                    <span className="suggestion-savings">~{s.savings_pct}% sort cost reduction</span>
                  )}
                </div>
                <div className="suggestion-desc">{s.description}</div>
                {s.example && (
                  <div className="suggestion-example">
                    <code>{s.example}</code>
                  </div>
                )}
                {s.note && (
                  <div className="suggestion-note">⚠ {s.note}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Footer ── */}
      <div className="index-analyzed-row">
        <span style={{ color:'var(--text-muted)', fontSize:12 }}>
          Analyzed {indexAnalysis.columns_analyzed} column reference(s) across
          WHERE · JOIN ON · ORDER BY · GROUP BY
        </span>
      </div>
    </div>
  )
}
