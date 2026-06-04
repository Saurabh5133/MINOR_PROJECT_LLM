import React, { useState } from 'react'

export default function ResultPanel({ result }) {
  const [showCandidates, setShowCandidates] = useState(false)
  const improved = result.improved && result.improvement_percent > 0

  return (
    <div className="result-panel animate-fade">

      {/* Banner */}
      <div className={`improvement-banner ${improved ? 'improved' : 'no-change'}`}>
        <div className="banner-left">
          <div className="banner-icon">{improved ? '✅' : 'ℹ️'}</div>
          <div>
            <div className="banner-title">
              {improved ? 'Query Optimized Successfully' : 'No Further Optimization Found'}
            </div>
            <div className="banner-sub">
              {improved
                ? `Rule applied: "${result.optimization_rule?.replace(/_/g, ' ')}"`
                : 'Query is already efficient — see explanation for details'}
            </div>
          </div>
        </div>
        {improved && <div className="improvement-badge">↓{result.improvement_percent}%</div>}
      </div>

      {/* MySQL real execution time */}
      {result.mode === 'mysql_real' && result.real_time_before_ms !== undefined && (
        <div>
          <div className="section-title">
            Real Execution Time
            <span className="mysql-mode-badge" style={{ marginLeft:10 }}>🐬 Real MySQL EXPLAIN</span>
          </div>
          <div className="real-time-row">
            <div className="real-time-box" style={{ borderColor:'rgba(255,71,87,0.3)' }}>
              <div className="cost-label">Before Optimization</div>
              <div className="real-time-val" style={{ color:'var(--red)' }}>
                {result.real_time_before_ms}
              </div>
              <div className="real-time-unit">milliseconds</div>
            </div>
            <div style={{ fontSize:24, color:'var(--text-muted)', alignSelf:'center' }}>→</div>
            <div className="real-time-box" style={{ borderColor:'rgba(0,230,118,0.3)' }}>
              <div className="cost-label">After Optimization</div>
              <div className="real-time-val" style={{ color:'var(--green)' }}>
                {result.real_time_after_ms}
              </div>
              <div className="real-time-unit">milliseconds</div>
            </div>
            {result.time_improvement_pct > 0 && (
              <div style={{ alignSelf:'center', fontFamily:'var(--font-mono)', fontSize:28, fontWeight:800, color:'var(--green)' }}>
                ↓{result.time_improvement_pct}%
              </div>
            )}
          </div>
        </div>
      )}

      {/* Cost comparison */}
      <div>
        <div className="section-title">Execution Cost</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>
          Unit = logical page I/O operations. 1 unit ≈ one 8KB page read from disk. Lower = faster &amp; cheaper.
        </div>
        <div className="cost-comparison">
          <div className="cost-box before">
            <div className="cost-label">Before Optimization</div>
            <div className="cost-number before">{result.cost_before?.toLocaleString()}</div>
            <div className="cost-unit">page I/O units</div>
          </div>
          <div className="cost-arrow">→</div>
          <div className="cost-box after">
            <div className="cost-label">After Optimization</div>
            <div className="cost-number after">{result.cost_after?.toLocaleString()}</div>
            <div className="cost-unit">page I/O units</div>
          </div>
        </div>
      </div>

      {/* Cost breakdown */}
      {result.cost_breakdown_before && (
        <div>
          <div className="section-title">Cost Breakdown</div>
          <CostBreakdown before={result.cost_breakdown_before} after={result.cost_breakdown_after} />
        </div>
      )}

      {/* Query comparison */}
      <div>
        <div className="section-title">Query Comparison</div>
        <div className="query-compare">
          <div className="query-box">
            <div className="query-box-header">
              <span className="query-box-title">Original</span>
              <span className="query-tag original">BEFORE</span>
            </div>
            <pre className="query-code">{result.original_query}</pre>
          </div>
          <div className="query-box">
            <div className="query-box-header">
              <span className="query-box-title">Optimized</span>
              <span className="query-tag optimized">AFTER</span>
            </div>
            <pre className="query-code">{result.optimized_query}</pre>
          </div>
        </div>
      </div>

      {/* SQLite execution plans */}
      <div>
        <div className="section-title">SQLite Execution Plans (EXPLAIN QUERY PLAN)</div>
        <div className="query-compare">
          <ExecutionPlan title="Before" plan={result.execution_plan_before} />
          <ExecutionPlan title="After"  plan={result.execution_plan_after}  />
        </div>
      </div>

      {/* ML strategy */}
      {result.ml_strategy && (
        <div>
          <div className="section-title">ML Model Analysis</div>
          <div className="ml-card">
            <div className="ml-main">
              <span className="ml-icon">🤖</span>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>Recommended Strategy</div>
                <div className="ml-strategy">{result.ml_strategy.recommended_strategy?.replace(/_/g, ' ')}</div>
              </div>
              <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>ML Cost Est.</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color: 'var(--purple)', fontWeight: 700 }}>
                  {result.ml_strategy.ml_estimated_cost?.toLocaleString()}
                </div>
              </div>
            </div>
            <div className="ml-bars">
              {result.ml_strategy.top_strategies?.map((s, i) => (
                <div key={i} className="ml-bar-row">
                  <div className="ml-bar-label">{s.strategy.replace(/_/g, ' ')}</div>
                  <div className="ml-bar-track">
                    <div className="ml-bar-fill" style={{ width: `${(s.confidence * 100).toFixed(1)}%` }} />
                  </div>
                  <div className="ml-bar-pct">{(s.confidence * 100).toFixed(1)}%</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Explanation */}
      {result.explanation && (
        <div>
          <div className="section-title">Optimization Explanation</div>
          <div className="explanation-card">
            <ExplanationText text={result.explanation} />
          </div>
        </div>
      )}

      {/* LLM result */}
      {result.llm_result && (
        <div>
          <div className="section-title">
            🧠 LLM Rewrite
            {result.llm_result.provider && (
              <span style={{ fontSize: 11, color: 'var(--accent)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>
                via {result.llm_result.provider} ({result.llm_result.model})
              </span>
            )}
          </div>
          <div className="ml-card">
            {result.llm_result.success ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <span style={{ color: 'var(--green)', fontSize: 16 }}>✓</span>
                  <strong style={{ color: 'var(--green)' }}>LLM Rewrite Applied</strong>
                  {result.llm_result.confidence && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto', fontFamily: 'var(--font-mono)' }}>
                      confidence: {(result.llm_result.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {result.llm_result.explanation && (
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.6 }}>
                    {result.llm_result.explanation}
                  </div>
                )}
                {result.llm_result.changes?.length > 0 && (
                  <ul style={{ fontSize: 12, color: 'var(--text-muted)', paddingLeft: 16, marginBottom: 10 }}>
                    {result.llm_result.changes.map((c, i) => <li key={i} style={{ marginBottom: 3 }}>{c}</li>)}
                  </ul>
                )}
                <div style={{ background: 'var(--bg-3)', borderRadius: 6, padding: 12, marginTop: 8 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, letterSpacing: 1, textTransform: 'uppercase' }}>
                    LLM Rewritten Query
                  </div>
                  <pre style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', margin: 0 }}>
                    {result.llm_result.query}
                  </pre>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ color: result.llm_result.llm_available ? 'var(--orange)' : 'var(--red)', fontSize: 16, marginTop: 1 }}>
                  {result.llm_result.llm_available ? '⚠' : '✗'}
                </span>
                <div>
                  <strong style={{ color: result.llm_result.llm_available ? 'var(--orange)' : 'var(--red)', fontSize: 13 }}>
                    {result.llm_result.llm_available ? 'LLM attempt failed' : 'LLM not configured'}
                  </strong>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.6 }}>
                    {result.llm_result.error}
                    {result.llm_result.error?.includes('Allowlist') || result.llm_result.error?.includes('allowlist') ? (
                      <div style={{ marginTop: 8, padding: '8px 10px', background: 'var(--bg-3)', borderRadius: 6, fontSize: 11 }}>
                        <strong style={{ color: 'var(--orange)' }}>Quick Fix:</strong>{' '}
                        Go to{' '}
                        <a href="https://console.groq.com" target="_blank" rel="noreferrer"
                           style={{ color: 'var(--accent)' }}>console.groq.com</a>
                        {' '}→ Settings → remove Host Allowlist entries.
                        Or create a new API key with no restrictions and update{' '}
                        <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>ml-model/.env</code>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Candidates */}
      {result.candidates?.length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div className="section-title" style={{ margin: 0 }}>
              All Candidate Rewrites ({result.candidates.length})
            </div>
            <button onClick={() => setShowCandidates(v => !v)} style={{
              background: 'none', border: '1px solid var(--border)', borderRadius: 5,
              padding: '4px 10px', fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer'
            }}>
              {showCandidates ? 'Hide' : 'Show'}
            </button>
          </div>
          {showCandidates && (
            <div className="candidates-list animate-fade">
              {result.candidates.map((c, i) => {
                const isBest = c.rule === result.optimization_rule
                const badge  = isBest ? 'best' : c.is_better ? 'ok' : 'worse'
                return (
                  <div key={i} className={`candidate-item ${isBest ? 'best' : ''}`}>
                    <span className={`candidate-badge ${badge}`}>
                      {isBest ? '★ BEST' : c.is_better ? '↑ BETTER' : '→ SAME'}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div className="candidate-rule">{c.rule}</div>
                      <div className="candidate-desc">{c.description}</div>
                      <div className="candidate-cost">Cost: {c.cost?.toLocaleString()} units</div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Cost Breakdown bars ─────────────────────────────────────── */
function CostBreakdown({ before, after }) {
  const LABELS = {
    scan_cost:     'Table Scan',
    join_cost:     'Join',
    sort_cost:     'Sort (ORDER BY)',
    agg_cost:      'Aggregation',
    subquery_cost: 'Subquery',
  }
  const maxVal = Math.max(...Object.values(before || {}), 1)
  const rows = Object.entries(LABELS).filter(([k]) => (before?.[k] || 0) > 0 || (after?.[k] || 0) > 0)

  if (rows.length === 0) return null

  return (
    <div className="breakdown-table">
      {rows.map(([key, label]) => {
        const bv   = before?.[key] || 0
        const av   = after?.[key]  || 0
        const bPct = (bv / maxVal * 100).toFixed(1)
        const aPct = (av / maxVal * 100).toFixed(1)
        const saved = bv - av
        return (
          <div key={key} className="breakdown-row-bar">
            <div className="brow-label">{label}</div>
            <div className="brow-bars">
              <div className="brow-bar-wrap">
                <div className="brow-bar before-bar" style={{ width: `${bPct}%` }} />
                <span className="brow-val">{bv.toLocaleString(undefined, {maximumFractionDigits:0})}</span>
              </div>
              <div className="brow-bar-wrap">
                <div className="brow-bar after-bar" style={{ width: `${aPct}%` }} />
                <span className="brow-val">{av.toLocaleString(undefined, {maximumFractionDigits:0})}</span>
              </div>
            </div>
            {saved > 0 && (
              <div className="brow-saved">↓ {saved.toLocaleString(undefined, {maximumFractionDigits:0})}</div>
            )}
          </div>
        )
      })}
      <div className="breakdown-legend">
        <span className="leg before">■ Before</span>
        <span className="leg after">■ After</span>
      </div>
    </div>
  )
}

/* ── Execution plan ──────────────────────────────────────────── */
function ExecutionPlan({ title, plan }) {
  if (!plan) return null
  return (
    <div className="plan-box">
      <div className="query-box-header">
        <span className="query-box-title">{title}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
          cost: {plan.cost?.toLocaleString()}
        </span>
      </div>
      <div className="plan-steps">
        {plan.error && (
          <div style={{ fontSize: 12, color: 'var(--red)', padding: '4px 8px' }}>⚠ {plan.error}</div>
        )}
        {(!plan.steps || plan.steps.length === 0) && !plan.error && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '4px 8px' }}>No plan available</div>
        )}
        {plan.steps?.map((step, i) => (
          <div key={i} className="plan-step">
            <span className={`plan-step-type ${step.type || 'OTHER'}`}>{step.type || 'OP'}</span>
            {step.uses_index && <span className="index-badge">IDX</span>}
            <span className="plan-step-detail">{step.detail}</span>
            <span className="plan-step-cost">~{step.step_cost?.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Explanation text renderer (bold **text** support) ───────── */
function ExplanationText({ text }) {
  if (!text) return null
  return (
    <div style={{ whiteSpace: 'pre-line', fontSize: 13, lineHeight: 1.75, color: 'var(--text-secondary)' }}>
      {text.split('\n').map((line, i) => {
        // Bold **word** or text between backticks
        const parts = line.split(/(\*\*.*?\*\*|`.*?`)/g)
        return (
          <div key={i}>
            {parts.map((part, j) => {
              if (part.startsWith('**') && part.endsWith('**'))
                return <strong key={j} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
              if (part.startsWith('`') && part.endsWith('`'))
                return <code key={j} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', background: 'var(--bg-3)', padding: '1px 5px', borderRadius: 3 }}>{part.slice(1, -1)}</code>
              return part
            })}
          </div>
        )
      })}
    </div>
  )
}
