import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API = axios.create({ baseURL: '/api' })

export default function MySQLPanel({ onConnected, onDisconnect }) {
  const [form, setForm]             = useState({ host:'localhost', port:'3306', user:'root', password:'' })
  const [status, setStatus]         = useState(null)
  const [message, setMessage]       = useState('')
  const [databases, setDatabases]   = useState([])
  const [selectedDb, setSelectedDb] = useState('')
  const [schema, setSchema]         = useState(null)
  const [setupStatus, setSetupStatus] = useState(null)
  const [setupMsg, setSetupMsg]     = useState('')
  const [mysqlConnected, setMysqlConnected] = useState(false)
  const [dropping, setDropping]     = useState(false)
  const [activeTab, setActiveTab]   = useState('demo')
  const [pymysqlOk, setPymysqlOk]   = useState(null)  // null=checking, true, false

  useEffect(() => {
    checkPymysql()
  }, [])

  const checkPymysql = async () => {
    try {
      const r = await API.get('/mysql/check')
      setPymysqlOk(r.data.available)
      if (r.data.available) {
        // Also check if already connected
        const s = await API.get('/mysql/status')
        if (s.data.connected) {
          setMysqlConnected(true)
          setStatus('connected')
          setMessage(`Connected — database: ${s.data.database || 'none'}`)
          if (s.data.database) {
            setSelectedDb(s.data.database)
            loadSchema(s.data.database)
          }
          loadDatabases()
        }
      }
    } catch {
      setPymysqlOk(false)
    }
  }

  const connect = async () => {
    setStatus('connecting')
    setMessage('Connecting to MySQL...')
    try {
      const r = await API.post('/mysql/connect', form)
      if (r.data.success) {
        setStatus('connected')
        setMysqlConnected(true)
        setMessage(r.data.message)
        setDatabases(r.data.databases || [])
      } else {
        setStatus('error')
        setMessage(r.data.message || 'Connection failed')
      }
    } catch (e) {
      setStatus('error')
      setMessage(e.response?.data?.message || e.message || 'Connection failed')
    }
  }

  const loadDatabases = async () => {
    try {
      const r = await API.get('/mysql/databases')
      if (r.data.success) setDatabases(r.data.databases)
    } catch {}
  }

  const loadSchema = async (db) => {
    try {
      const r = await API.get(`/mysql/schema/${db}`)
      if (r.data.success) {
        setSchema(r.data.schema)
        onConnected({ database: db, schema: r.data.schema, mode: 'mysql' })
      }
    } catch {}
  }

  const selectDb = async (db) => {
    setSelectedDb(db)
    await loadSchema(db)
  }

  const setupDemo = async () => {
    setSetupStatus('loading')
    setSetupMsg('Creating demo database... this takes 30-60 seconds on first run')
    try {
      const r = await API.post('/mysql/setup-demo')
      if (r.data.success) {
        setSetupStatus('done')
        setSetupMsg(r.data.message)
        setSelectedDb('queryforge_demo')
        await loadSchema('queryforge_demo')
        await loadDatabases()
      } else {
        setSetupStatus('error')
        setSetupMsg(r.data.message)
      }
    } catch (e) {
      setSetupStatus('error')
      setSetupMsg(e.response?.data?.message || e.message)
    }
  }

  const dropDemo = async () => {
    if (!window.confirm('Drop queryforge_demo database? All demo data will be deleted.')) return
    setDropping(true)
    try {
      await API.post('/mysql/drop-demo')
      setSetupStatus(null); setSetupMsg('')
      setSelectedDb(''); setSchema(null)
      await loadDatabases()
    } catch {}
    setDropping(false)
  }

  // ── pymysql not installed ──────────────────────────────────────
  if (pymysqlOk === false) {
    return (
      <div className="mysql-panel animate-fade">
        <div className="mysql-header">
          <div className="mysql-logo">🐬</div>
          <div>
            <div className="mysql-title">MySQL Connection</div>
            <div className="mysql-sub">One package needs to be installed first</div>
          </div>
        </div>
        <div className="mysql-msg error">
          <strong>pymysql not installed</strong>
        </div>
        <div style={{ background:'var(--bg-3)', borderRadius:'var(--radius)', padding:'14px 16px' }}>
          <div style={{ fontSize:13, color:'var(--text-secondary)', marginBottom:10 }}>
            Run this command in your terminal, then restart <code style={{ color:'var(--accent)', fontFamily:'var(--font-mono)' }}>python app.py</code>:
          </div>
          <div style={{ background:'var(--bg-0)', border:'1px solid var(--border)', borderRadius:6, padding:'10px 14px', fontFamily:'var(--font-mono)', fontSize:13, color:'var(--green)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <span>pip install pymysql cryptography</span>
            <button
              onClick={() => navigator.clipboard.writeText('pip install pymysql cryptography')}
              style={{ background:'none', border:'1px solid var(--border)', borderRadius:4, padding:'3px 8px', color:'var(--text-muted)', cursor:'pointer', fontSize:11, fontFamily:'var(--font-body)' }}
            >
              Copy
            </button>
          </div>
          <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:10 }}>
            After installing, refresh this page.
          </div>
        </div>
      </div>
    )
  }

  // ── checking ──────────────────────────────────────────────────
  if (pymysqlOk === null) {
    return (
      <div className="mysql-panel">
        <div style={{ display:'flex', alignItems:'center', gap:10, color:'var(--text-muted)', fontSize:13 }}>
          <span className="spinner" style={{ border:'2px solid var(--border)', borderTopColor:'var(--accent)', width:16, height:16 }} />
          Checking MySQL dependencies...
        </div>
      </div>
    )
  }

  return (
    <div className="mysql-panel animate-fade">
      <div className="mysql-header">
        <div className="mysql-logo">🐬</div>
        <div>
          <div className="mysql-title">MySQL Connection</div>
          <div className="mysql-sub">Real EXPLAIN plans · Real execution time · No simulation</div>
        </div>
        {mysqlConnected && (
          <div className="mysql-status-badge">
            <span className="status-dot online" />
            Connected
          </div>
        )}
      </div>

      {/* Connection form */}
      {!mysqlConnected ? (
        <div className="mysql-form">
          <div className="mysql-form-grid">
            {[
              ['Host',     'host',     'localhost', 'text'],
              ['Port',     'port',     '3306',      'number'],
              ['Username', 'user',     'root',      'text'],
              ['Password', 'password', '••••••',    'password'],
            ].map(([label, key, placeholder, type]) => (
              <div key={key} className="mysql-field">
                <label className="mysql-label">{label}</label>
                <input
                  type={type}
                  className="mysql-input"
                  placeholder={placeholder}
                  value={form[key]}
                  onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
                />
              </div>
            ))}
          </div>

          <button
            className={`mysql-connect-btn ${status === 'connecting' ? 'loading' : ''}`}
            onClick={connect}
            disabled={status === 'connecting'}
          >
            {status === 'connecting'
              ? <><span className="spinner" /> Connecting...</>
              : '🔌 Connect to MySQL'}
          </button>

          {message && (
            <div className={`mysql-msg ${status === 'error' ? 'error' : status === 'connected' ? 'success' : 'info'}`}>
              {message}
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="mysql-tabs">
            <button className={`mysql-tab ${activeTab==='demo' ? 'active':''}`} onClick={() => setActiveTab('demo')}>
              🎯 Demo Data
            </button>
            <button className={`mysql-tab ${activeTab==='own' ? 'active':''}`} onClick={() => setActiveTab('own')}>
              🗄️ Your Database
            </button>
          </div>

          {/* Demo tab */}
          {activeTab === 'demo' && (
            <div className="mysql-tab-content animate-fade">
              <div className="mysql-demo-info">
                <div style={{ fontSize:13, color:'var(--text-secondary)', marginBottom:10, lineHeight:1.7 }}>
                  Creates <code style={{ color:'var(--accent)', fontFamily:'var(--font-mono)' }}>queryforge_demo</code> with
                  7 tables and realistic data.
                  <span style={{ color:'var(--green)', fontSize:12, display:'block', marginTop:4 }}>
                    ✓ Inserted once — reused forever — storage stays at ~15MB
                  </span>
                </div>
                <div className="mysql-demo-tables">
                  {[['customers','10K'],['orders','50K'],['products','5K'],
                    ['employees','8K'],['transactions','100K'],['flights','20K'],['patients','15K']
                  ].map(([t,r]) => (
                    <div key={t} className="mysql-demo-table-chip">
                      <span className="mono" style={{ color:'var(--accent)', fontSize:12 }}>{t}</span>
                      <span style={{ color:'var(--text-muted)', fontSize:10 }}>{r} rows</span>
                    </div>
                  ))}
                </div>
              </div>

              {setupStatus === 'done' && selectedDb === 'queryforge_demo' ? (
                <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                  <div className="mysql-msg success">✓ {setupMsg}</div>
                  <button className="mysql-drop-btn" onClick={dropDemo} disabled={dropping}>
                    {dropping ? 'Dropping...' : '🗑 Clear Demo Data'}
                  </button>
                </div>
              ) : (
                <button
                  className={`mysql-connect-btn ${setupStatus==='loading' ? 'loading':''}`}
                  onClick={setupDemo}
                  disabled={setupStatus === 'loading'}
                >
                  {setupStatus === 'loading'
                    ? <><span className="spinner" /> Creating demo data...</>
                    : '⚡ Setup Demo Database'}
                </button>
              )}

              {setupMsg && setupStatus !== 'done' && (
                <div className={`mysql-msg ${setupStatus==='error' ? 'error':'info'}`}>
                  {setupMsg}
                </div>
              )}
            </div>
          )}

          {/* Own DB tab */}
          {activeTab === 'own' && (
            <div className="mysql-tab-content animate-fade">
              <div style={{ fontSize:13, color:'var(--text-secondary)', marginBottom:10 }}>
                Select an existing database. Your data is <strong>never modified</strong> — read only.
              </div>
              <div className="mysql-db-list">
                {databases.length === 0
                  ? <div style={{ color:'var(--text-muted)', fontSize:13 }}>No user databases found</div>
                  : databases.map(db => (
                    <button key={db}
                      className={`mysql-db-btn ${selectedDb===db ? 'active':''}`}
                      onClick={() => selectDb(db)}
                    >
                      🗄️ {db}
                      {selectedDb===db && <span style={{ marginLeft:'auto', color:'var(--green)' }}>✓ selected</span>}
                    </button>
                  ))
                }
              </div>
            </div>
          )}

          {/* Schema preview */}
          {schema && selectedDb && (
            <div className="mysql-schema-preview animate-fade">
              <div className="mysql-schema-header">
                <span style={{ fontWeight:700, color:'var(--text-primary)' }}>
                  📋 <span style={{ color:'var(--accent)', fontFamily:'var(--font-mono)' }}>{selectedDb}</span>
                </span>
                <span style={{ fontSize:12, color:'var(--text-muted)' }}>
                  {Object.keys(schema).length} tables · ready to query
                </span>
              </div>
              <div className="mysql-schema-tables">
                {Object.entries(schema).map(([tbl, info]) => (
                  <div key={tbl} className="mysql-schema-table">
                    <div className="mysql-schema-tbl-name">
                      <span className="mono">{tbl}</span>
                      <span className="mysql-row-badge">{info.row_count?.toLocaleString()} rows</span>
                      {info.indexed_columns?.size > 0 && (
                        <span style={{ fontSize:10, color:'var(--green)' }}>
                          {info.indexed_columns.size} indexed
                        </span>
                      )}
                    </div>
                    <div className="mysql-schema-cols">
                      {info.columns?.slice(0,7).join(', ')}
                      {info.columns?.length > 7 && ` +${info.columns.length - 7} more`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
