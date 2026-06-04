import React from 'react'

export default function QueryInput({ value, onChange }) {
  const format = () => {
    let q = value
      .replace(/\s+/g, ' ')
      .replace(/\bSELECT\b/gi, 'SELECT')
      .replace(/\bFROM\b/gi, '\nFROM')
      .replace(/\bWHERE\b/gi, '\nWHERE')
      .replace(/\bAND\b/gi, '\n  AND')
      .replace(/\bOR\b/gi, '\n  OR')
      .replace(/\b(LEFT |RIGHT |INNER |FULL )?JOIN\b/gi, (m) => '\n' + m.trim())
      .replace(/\bGROUP BY\b/gi, '\nGROUP BY')
      .replace(/\bORDER BY\b/gi, '\nORDER BY')
      .replace(/\bHAVING\b/gi, '\nHAVING')
      .replace(/\bLIMIT\b/gi, '\nLIMIT')
      .trim()
    onChange(q)
  }

  return (
    <div className="editor-panel">
      <div className="editor-header">
        <span className="editor-title">SQL Query</span>
        <div className="editor-actions">
          <button className="editor-btn" onClick={format}>Format</button>
          <button className="editor-btn" onClick={() => onChange('')}>Clear</button>
        </div>
      </div>
      <textarea
        className="sql-textarea"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={"SELECT *\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nWHERE o.amount > 500"}
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
      />
    </div>
  )
}
