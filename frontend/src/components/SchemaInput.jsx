import React, { useState } from 'react'

export default function SchemaInput({ value, onChange }) {
  const [error, setError] = useState(null)

  const validate = (v) => {
    try { JSON.parse(v); setError(null) } catch { setError('Invalid JSON') }
    onChange(v)
  }

  const pretty = () => {
    try { onChange(JSON.stringify(JSON.parse(value), null, 2)); setError(null) }
    catch { setError('Cannot format: Invalid JSON') }
  }

  return (
    <div className="editor-panel">
      <div className="editor-header">
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span className="editor-title">Schema (JSON)</span>
          {error && <span style={{ fontSize:11, color:'var(--red)' }}>⚠ {error}</span>}
        </div>
        <button className="editor-btn" onClick={pretty}>Prettify</button>
      </div>
      <textarea
        className="sql-textarea"
        value={value}
        onChange={e => validate(e.target.value)}
        placeholder={'{\n  "table_name": {\n    "columns": ["id", "name", ...],\n    "row_count": 10000\n  }\n}'}
        spellCheck={false}
        style={{ fontFamily:'var(--font-mono)', fontSize:12 }}
      />
    </div>
  )
}
