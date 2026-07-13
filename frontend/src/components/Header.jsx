import React from 'react'

export default function Header({ serviceStatus, llmStatus }) {
  return (
    <header className="header">
      <div className="header-brand">
        <div className="header-logo">SE</div>
        <div>
          <div className="header-title">MultiCloud Query Cost Analyzer and Recommendation System</div>
          <div className="header-sub">SQL Optimization Engine</div>
        </div>
      </div>
      <div className="header-right">
        {llmStatus && (
          <div
            className="status-badge"
            title={llmStatus.message}
            style={{ borderColor: llmStatus.enabled ? 'rgba(0,212,255,0.3)' : undefined }}
          >
            <div className={`status-dot ${llmStatus.enabled ? 'online' : 'offline'}`} />
            <span>
              {llmStatus.enabled
                ? `${llmStatus.provider} (${llmStatus.model})`
                : 'LLM off'}
            </span>
          </div>
        )}
        <div className="status-badge">
          <div className={`status-dot ${serviceStatus}`} />
          <span>ML {serviceStatus}</span>
        </div>
      </div>
    </header>
  )
}
