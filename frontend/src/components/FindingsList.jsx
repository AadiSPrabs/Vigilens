import React, { useState } from 'react'
import SeverityBadge from './SeverityBadge'

export default function FindingsList({ audit, selectedId, onSelectPerson }) {
  const [expanded, setExpanded] = useState({})
  
  const toggleExpand = (key) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
  }
  
  const getPPELabel = (value) => {
    if (value === 'unknown') return 'Unclear - needs human check'
    if (value === 'present') return 'Present'
    if (value === 'absent') return 'Absent'
    return value
  }
  
  if (!Array.isArray(audit.persons) || audit.persons.length === 0) {
    return (
      <div className="card">
        <h2>Findings</h2>
        <p style={{ color: 'var(--critical)' }}>No people detected; not a safety clearance.</p>
      </div>
    )
  }
  
  if (!Array.isArray(audit.zones) || audit.zones.length === 0) {
    return (
      <div className="card">
        <h2>Findings</h2>
        <p style={{ color: 'var(--medium)' }}>No zones were checked; this is not proof the area is safe.</p>
      </div>
    )
  }
  
  const allFindings = []
  ;(audit.persons || []).forEach((person, pIdx) => {
    (person.findings || []).forEach((finding, fIdx) => {
      const findingKey = finding.id || `${person.id}:${finding.rule_id}:${fIdx}`
      allFindings.push({ person, finding, pIdx, fIdx, key: findingKey })
    })
  })
  
  if (allFindings.length === 0) {
    return (
      <div className="card">
        <h2>Findings</h2>
        <p style={{ color: 'var(--success)' }}>✓ No findings - site is compliant</p>
      </div>
    )
  }
  
  return (
    <div className="card">
      <h2>Findings ({allFindings.length})</h2>
      <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
        {allFindings.map(({ person, finding, pIdx, key }) => {
          // Use finding's zone_id, fall back to person.zone_id
          const zoneId = finding.zone_id !== undefined ? finding.zone_id : person.zone_id
          const zoneName = zoneId ? (audit.zones?.find(z => z.id === zoneId)?.name || 'Unknown zone') : 'Outside all zones'
          const isSelected = selectedId === person.id
          const isUncertainty = finding.kind === 'uncertainty'
          
          return (
            <div 
              key={key}
              style={{ 
                border: isSelected ? '2px solid var(--primary)' : '1px solid var(--border)',
                padding: '0.75rem',
                marginBottom: '0.75rem',
                borderRadius: '4px',
                background: isSelected ? 'rgba(59, 130, 246, 0.1)' : 'var(--bg)'
              }}
            >
              <button
                onClick={() => onSelectPerson(person.id)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text)',
                  cursor: 'pointer',
                  padding: 0,
                  fontSize: '1rem',
                  fontWeight: '600'
                }}
                aria-label={`Select Person ${pIdx + 1}`}
              >
                Person {pIdx + 1} • {zoneName}
              </button>
              
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.875rem' }}>Hard hat: <strong>{getPPELabel(person.helmet)}</strong></span>
                <span style={{ fontSize: '0.875rem' }}>Vest: <strong>{getPPELabel(person.vest)}</strong></span>
              </div>
              
              <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                {isUncertainty ? (
                  <span 
                    style={{ 
                      color: '#92400e', 
                      background: '#fef3c7', 
                      padding: '0.25rem 0.5rem', 
                      borderRadius: '4px',
                      fontSize: '0.875rem',
                      fontWeight: '600'
                    }}
                  >
                    Uncertain - needs human check
                  </span>
                ) : (
                  <SeverityBadge severity={finding.severity} />
                )}
                <code style={{ fontSize: '0.75rem', background: 'var(--panel)', padding: '0.25rem' }}>{finding.rule_id}</code>
              </div>
              
              <p style={{ margin: '0.5rem 0', fontSize: '0.9rem' }}>{finding.message}</p>
              
              {finding.recheck_trace && finding.recheck_trace.length > 0 && (
                <div>
                  <button
                    onClick={() => toggleExpand(key)}
                    className="btn btn-secondary"
                    style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                  >
                    {expanded[key] ? 'Hide' : 'Show'} How was this checked?
                  </button>
                  {expanded[key] && (
                    <ul style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                      {finding.recheck_trace.map((trace, i) => (
                        <li key={i}>{trace}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
