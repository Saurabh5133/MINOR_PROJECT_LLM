import React, { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import './App.css'
import QueryInput       from './components/QueryInput'
import SchemaInput      from './components/SchemaInput'
import ResultPanel      from './components/ResultPanel'
import CloudCostPanel   from './components/CloudCostPanel'
import IndexAdvisorPanel from './components/IndexAdvisorPanel'
import MySQLPanel       from './components/MySQLPanel'
import Header           from './components/Header'

const API = axios.create({ baseURL: '/api' })

const EXAMPLE_QUERIES = [
  {
    label: 'JOIN + Filter',
    query: `SELECT *\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nWHERE o.amount > 500\nORDER BY o.created_at DESC`,
    schema: {
      orders:    { columns: ['id','customer_id','amount','status','created_at','notes'], row_count: 50000 },
      customers: { columns: ['id','name','email','city','country'], row_count: 10000 }
    }
  },
  {
    label: 'Aggregate',
    query: `SELECT department_id, COUNT(*) as headcount, AVG(salary) as avg_sal\nFROM employees\nWHERE hire_date > '2020-01-01'\nAND employment_type = 'full_time'\nGROUP BY department_id\nHAVING COUNT(*) > 5`,
    schema: {
      employees: { columns: ['id','name','email','department_id','salary','hire_date','employment_type','manager_id','performance_score'], row_count: 900000 }
    }
  },
  {
    label: 'Subquery (IN)',
    query: `SELECT *\nFROM products\nWHERE category_id IN (\n  SELECT id FROM categories WHERE status = 'active'\n)\nAND price < 500`,
    schema: {
      products:   { columns: ['id','name','price','category_id','stock','created_at'], row_count: 25000 },
      categories: { columns: ['id','name','status','description'], row_count: 500 }
    }
  },
  {
    label: 'Simple Filter',
    query: `SELECT id, username, email, last_login\nFROM users\nWHERE country = 'Germany'\nAND is_active = 1`,
    schema: {
      users: { columns: ['id','username','email','password_hash','country','city','is_active','last_login','created_at'], row_count: 8000000 }
    }
  },
  {
    label: 'OR → IN',
    query: `SELECT id, case_number, crime_type, city\nFROM crime_reports\nWHERE severity = 'high'\nOR severity = 'critical'\nOR severity = 'extreme'`,
    schema: {
      crime_reports: { columns: ['id','case_number','crime_type','severity','status','city','reported_at','description'], row_count: 1500000 }
    }
  },
  {
    label: 'DISTINCT on PK',
    query: `SELECT DISTINCT id, username, country, plan_type\nFROM subscribers\nWHERE plan_type = 'premium'\nAND is_cancelled = 0`,
    schema: {
      subscribers: { columns: ['id','username','email','country','plan_type','is_cancelled','renewal_date','seats'], row_count: 500000 }
    }
  },
]

// MySQL demo table sample queries
const MYSQL_DEMO_QUERIES = [
  {
    label: 'Customers (MySQL)',
    query: `SELECT * FROM customers\nWHERE country = 'USA'\nAND is_active = 1\nAND age > 30`,
    database: 'queryforge_demo'
  },
  {
    label: 'Orders JOIN (MySQL)',
    query: `SELECT o.id, o.amount, o.status, c.first_name, c.country\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nWHERE o.amount > 1000\nAND o.status = 'pending'\nORDER BY o.created_at DESC`,
    database: 'queryforge_demo'
  },
  {
    label: 'Transactions (MySQL)',
    query: `SELECT customer_id, COUNT(*) as total_txn, SUM(amount) as total_amount\nFROM transactions\nWHERE is_flagged = 1\nAND amount > 5000\nGROUP BY customer_id\nHAVING COUNT(*) > 2`,
    database: 'queryforge_demo'
  },
  {
    label: 'Flights (MySQL)',
    query: `SELECT * FROM flights\nWHERE status = 'delayed'\nAND delay_minutes > 60\nORDER BY departure_time DESC`,
    database: 'queryforge_demo'
  },
  {
    label: 'Patients (MySQL)',
    query: `SELECT * FROM patients\nWHERE severity = 'critical'\nAND age > 60\nORDER BY admitted_at DESC`,
    database: 'queryforge_demo'
  },
]

export default function App() {
  const [mode, setMode]           = useState('standard')   // 'standard' | 'mysql'
  const [query, setQuery]         = useState(EXAMPLE_QUERIES[0].query)
  const [schema, setSchema]       = useState(JSON.stringify(EXAMPLE_QUERIES[0].schema, null, 2))
  const [mysqlDb, setMysqlDb]     = useState('')
  const [mysqlSchema, setMysqlSchema] = useState(null)
  const [useLLM, setUseLLM]       = useState(false)
  const [calcCloud, setCalcCloud] = useState(true)
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)
  const [activeTab, setActiveTab] = useState('query')
  const [llmStatus, setLlmStatus] = useState(null)
  const [serviceStatus, setServiceStatus] = useState('checking')

  useEffect(() => { checkHealth() }, [])

  const checkHealth = async () => {
    try {
      const r = await API.get('/health')
      setServiceStatus(r.data.status === 'ok' ? 'online' : 'degraded')
      setLlmStatus(r.data.ml_service?.llm)
    } catch { setServiceStatus('offline') }
  }

  // Called when MySQL connects and schema is loaded
  const handleMysqlConnected = ({ database, schema: sch, mode: m }) => {
    setMysqlDb(database)
    setMysqlSchema(sch)
    // Set first table's query as example
    const tables = Object.keys(sch)
    if (tables.length > 0) {
      const firstTbl = tables[0]
      setQuery(`SELECT * FROM ${firstTbl} LIMIT 100`)
    }
  }

  const loadExample = (ex) => {
    if (ex.database) {
      // MySQL example
      setQuery(ex.query)
      setMysqlDb(ex.database)
      setMode('mysql')
    } else {
      setQuery(ex.query)
      setSchema(JSON.stringify(ex.schema, null, 2))
      setMode('standard')
    }
    setResult(null)
    setError(null)
    setActiveTab('query')
  }

  const handleOptimize = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      let res

      if (mode === 'mysql' && mysqlDb) {
        // ── MySQL mode: real EXPLAIN ──
        res = await API.post('/mysql/optimize', {
          query,
          database: mysqlDb,
          use_llm:  useLLM,
        })
      } else {
        // ── Standard mode: SQLite simulation ──
        let parsedSchema = {}
        try {
          parsedSchema = JSON.parse(schema || '{}')
        } catch {
          setError('Invalid JSON in schema. Please check the format.')
          setLoading(false)
          return
        }
        res = await API.post('/optimize', {
          query,
          schema: parsedSchema,
          use_llm: useLLM,
          calculate_cloud_cost: calcCloud,
        })
      }

      setResult(res.data)
      setActiveTab('results')
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }, [query, schema, useLLM, calcCloud, mode, mysqlDb])

  const isMysqlReady = mode === 'mysql' && mysqlDb

  return (
    <div className="app">
      <Header serviceStatus={serviceStatus} llmStatus={llmStatus} />

      <div className="app-body">
        {/* ── Sidebar ── */}
        <aside className="sidebar">

          {/* Mode toggle */}
          <div className="sidebar-section">
            <div className="sidebar-label">Mode</div>
            <div className="mode-toggle-row">
              <button
                className={`mode-btn ${mode === 'standard' ? 'active' : ''}`}
                onClick={() => { setMode('standard'); setResult(null) }}
              >
                📊 Standard
              </button>
              {/* <button
                className={`mode-btn ${mode === 'mysql' ? 'active' : ''}`}
                onClick={() => { setMode('mysql'); setResult(null) }}
              >
                🐬 MySQL
              </button> */}
            </div>
            {mode === 'mysql' && (
              <div style={{ fontSize:11, color: isMysqlReady ? 'var(--green)' : 'var(--orange)', marginTop:6 }}>
                {isMysqlReady ? `✓ DB: ${mysqlDb}` : '⚠ Connect MySQL first'}
              </div>
            )}
          </div>

          {/* Examples */}
          <div className="sidebar-section">
            <div className="sidebar-label">
              {mode === 'mysql' ? 'MySQL Examples' : 'Examples'}
            </div>
            {(mode === 'mysql' ? MYSQL_DEMO_QUERIES : EXAMPLE_QUERIES).map((ex, i) => (
              <button key={i} className="example-btn" onClick={() => loadExample(ex)}>
                <span className="example-icon">▸</span>{ex.label}
              </button>
            ))}
          </div>

          {/* Options */}
          <div className="sidebar-section">
            <div className="sidebar-label">Options</div>
            <label className="toggle-row">
              <span>LLM Rewrite</span>
              <div
                className={`toggle ${useLLM ? 'on' : ''} ${!llmStatus?.enabled ? 'disabled' : ''}`}
                onClick={() => llmStatus?.enabled && setUseLLM(v => !v)}
                title={llmStatus?.enabled
                  ? `Using ${llmStatus.provider} (${llmStatus.model})`
                  : 'Set OPENAI_API_KEY in ml-model/.env'}
              >
                <div className="toggle-thumb" />
              </div>
            </label>
            {!llmStatus?.enabled && (
              <div className="llm-hint">
                Create a free key at{' '}
                <a href="https://console.groq.com" target="_blank" rel="noreferrer">console.groq.com</a>
                {' '}then add to <code>ml-model/.env</code>
              </div>
            )}
            {mode === 'standard' && (
              <label className="toggle-row">
                <span>Cloud Costs</span>
                <div className={`toggle ${calcCloud ? 'on' : ''}`} onClick={() => setCalcCloud(v => !v)}>
                  <div className="toggle-thumb" />
                </div>
              </label>
            )}
          </div>

          {/* Quick stats */}
          {result && (
            <div className="sidebar-section">
              <div className="sidebar-label">Quick Stats</div>
              {result.mode === 'mysql_real' && result.real_time_before_ms !== undefined ? (
                <>
                  <div className="stat-card">
                    <div className="stat-label">Time Before</div>
                    <div className="stat-value red">{result.real_time_before_ms} ms</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Time After</div>
                    <div className="stat-value green">{result.real_time_after_ms} ms</div>
                  </div>
                </>
              ) : (
                <>
                  <div className="stat-card">
                    <div className="stat-label">Cost Before</div>
                    <div className="stat-value red">{result.cost_before?.toLocaleString()}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Cost After</div>
                    <div className="stat-value green">{result.cost_after?.toLocaleString()}</div>
                  </div>
                </>
              )}
              <div className="stat-card">
                <div className="stat-label">Improvement</div>
                <div className="stat-value accent">{result.improvement_percent}%</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Rule Applied</div>
                <div className="stat-value small">{result.optimization_rule?.replace(/_/g,' ')}</div>
              </div>
              {result.index_analysis?.total_count > 0 && (
                <div className="stat-card" style={{ borderColor:'var(--orange)' }}>
                  <div className="stat-label">Missing Indexes</div>
                  <div className="stat-value" style={{ color:'var(--orange)' }}>
                    {result.index_analysis.total_count}
                  </div>
                </div>
              )}
            </div>
          )}
        </aside>

        {/* ── Main ── */}
        <main className="main-content">
          <div className="tabs">
            {['query','results','cloud','indexes','trace'].map(tab => (
              <button
                key={tab}
                className={`tab ${activeTab === tab ? 'active' : ''}
                  ${tab !== 'query' && !result ? 'disabled' : ''}
                  ${tab === 'cloud' && mode === 'mysql' ? 'disabled' : ''}`}
                onClick={() => {
                  if (tab === 'query') setActiveTab(tab)
                  else if (result && !(tab === 'cloud' && mode === 'mysql')) setActiveTab(tab)
                }}
              >
                {tab === 'query'   && '⬡ Query Editor'}
                {tab === 'results' && '⬡ Results'}
                {tab === 'cloud'   && '⬡ Cloud Costs'}
                {tab === 'indexes' && '⬡ Index Advisor'}
                {tab === 'trace'   && '⬡ Trace'}
                {tab === 'results' && result?.improved && (
                  <span className="tab-badge green">↓{result.improvement_percent}%</span>
                )}
                {tab === 'indexes' && result?.index_analysis?.total_count > 0 && (
                  <span className="tab-badge" style={{ background:'rgba(255,160,64,0.15)', color:'var(--orange)' }}>
                    {result.index_analysis.total_count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="tab-content">

            {/* ── Query Editor tab ── */}
            {activeTab === 'query' && (
              <div className="animate-fade">

                {/* MySQL connection panel */}
                {mode === 'mysql' && (
                  <div style={{ marginBottom: 16 }}>
                    <MySQLPanel
                      onConnected={handleMysqlConnected}
                      onDisconnect={() => { setMysqlDb(''); setMysqlSchema(null) }}
                    />
                  </div>
                )}

                {/* Query + Schema editors */}
                <div className={mode === 'mysql' ? '' : 'editor-grid'}>
                  <QueryInput value={query} onChange={setQuery} />
                  {mode === 'standard' && (
                    <SchemaInput value={schema} onChange={setSchema} />
                  )}
                  {mode === 'mysql' && mysqlSchema && (
                    <div className="editor-panel">
                      <div className="editor-header">
                        <span className="editor-title">Schema (auto-read from MySQL)</span>
                        <span style={{ fontSize:11, color:'var(--green)', fontFamily:'var(--font-mono)' }}>
                          {Object.keys(mysqlSchema).length} tables
                        </span>
                      </div>
                      <div style={{ padding:14, overflow:'auto', maxHeight:240 }}>
                        {Object.entries(mysqlSchema).map(([tbl, info]) => (
                          <div key={tbl} style={{ marginBottom:8 }}>
                            <span style={{ fontFamily:'var(--font-mono)', color:'var(--accent)', fontSize:13 }}>{tbl}</span>
                            <span style={{ color:'var(--text-muted)', fontSize:11, marginLeft:8 }}>
                              ({info.row_count?.toLocaleString()} rows)
                            </span>
                            <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-muted)', marginTop:2 }}>
                              {info.columns?.join(', ')}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {error && (
                  <div className="error-box animate-fade">
                    <span>⚠</span><span>{error}</span>
                  </div>
                )}

                <div className="action-row">
                  <button
                    className={`btn-optimize ${loading ? 'loading' : ''}`}
                    onClick={handleOptimize}
                    disabled={loading || !query.trim() || (mode === 'mysql' && !mysqlDb)}
                    title={mode === 'mysql' && !mysqlDb ? 'Connect to MySQL first' : ''}
                  >
                    {loading
                      ? <><span className="spinner" />Analyzing...</>
                      : <><span>⚡</span>{mode === 'mysql' ? 'Optimize (Real MySQL)' : 'Optimize Query'}</>}
                  </button>
                  <span className="action-hint">
                    {mode === 'mysql'
                      ? 'Real EXPLAIN · Real execution time · Rule rewrites · Index recommendations'
                      : 'ML strategy · Rule rewrites · SQLite plans · Cloud cost estimates'}
                  </span>
                </div>
              </div>
            )}

            {/* ── Results tab ── */}
            {activeTab === 'results' && result && (
              <ResultPanel result={result} />
            )}

            {/* ── Cloud Costs tab ── */}
            {activeTab === 'cloud' && result?.cloud_costs && mode !== 'mysql' && (
              <CloudCostPanel cloudCosts={result.cloud_costs} />
            )}

            {/* ── Index Advisor tab ── */}
            {activeTab === 'indexes' && result && (
              <IndexAdvisorPanel indexAnalysis={result.index_analysis} />
            )}

            {/* ── Trace tab ── */}
            {activeTab === 'trace' && result && (
              <div className="trace-panel animate-fade">
                <div className="section-title">Pipeline Execution Trace</div>
                {result.mode === 'mysql_real' && (
                  <div className="mysql-mode-badge" style={{ marginBottom:12 }}>
                    🐬 MySQL Real Mode — database: {result.database}
                  </div>
                )}
                {result.trace?.map((step, i) => (
                  <div key={i} className="trace-step animate-slide"
                    style={{ animationDelay:`${i * 0.04}s` }}>
                    <div className="trace-idx">{String(i+1).padStart(2,'0')}</div>
                    <div className="trace-body">
                      <div className="trace-name">{step.step}</div>
                      {step.data && (
                        <pre className="trace-data">{JSON.stringify(step.data, null, 2)}</pre>
                      )}
                    </div>
                  </div>
                ))}
                <div className="trace-elapsed">
                  Total: <strong>{result.elapsed_seconds}s</strong>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
