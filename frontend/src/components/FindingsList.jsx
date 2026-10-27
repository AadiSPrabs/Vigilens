import React, { useState } from 'react'
import SeverityBadge from './SeverityBadge'

function getZoneLabel(audit, person, finding) {
  const zoneId = finding.zone_id !== undefined ? finding.zone_id : person.zone_id
  const membership = audit.zone_membership_status
  const zoneIds = audit.zone_ids
  
  if (zoneId !== null && zoneId !== undefined) {
    if (Array.isArray(audit.zones)) {
      const zone = audit.zones.find(z => z.id === zoneId)
      if (zone) return zone.name
    }
    return 'Unknown zone'
  }
  
  if (membership === 'unknown') {
    return 'Zone unknown: ground contact uncertain, needs review'
  }
  if (membership === 'known') {
    if (Array.isArray(zoneIds) && zoneIds.length === 0) {
      if (Array.isArray(audit.zones) && audit.zones.length > 0) {
        return 'Outside all drawn zones'
      }
      return 'No zones were checked'
    }
    if (Array.isArray(zoneIds) && zoneIds.length > 0) {
      const names = zoneIds.map(zid => audit.zones?.find(z => z.id === zid)?.name).filter(Boolean)
      if (names.length > 0) return names.join(', ')
    }
  }
  return 'No zone shown'
}

export default function FindingsList({ audit, selectedId, onSelectPerson, decisions, setDecisions, filters, setFilters, showHeader = true }) {
  const [expanded, setExpanded] = useState({})
  if (!audit) return null
  const handlePrint = () => { if (typeof window !== 'undefined') window.print() }
  
  const toggleExpand = (key) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
  }
  
  const getPPELabel = (value) => {
    if (value === 'unknown') return 'Unclear - needs human check'
    if (value === 'present') return 'Present'
    if (value === 'absent') return 'Absent'
    return value
  }

  const printAction = showHeader ? (
    <div className="findings-print">
      <button type="button" className="btn btn-secondary" onClick={handlePrint} aria-label="Print or export PDF">
        Print / Export PDF
      </button>
    </div>
  ) : null
  
  if (!Array.isArray(audit.persons) || audit.persons.length === 0) {
    return (
      <>
        {printAction}
        <div className="card">
          <h2>Findings</h2>
          <p style={{ color: 'var(--critical)' }}>No people detected; not a safety clearance.</p>
        </div>
      </>
    )
  }
  
  if (!Array.isArray(audit.zones) || audit.zones.length === 0) {
    return (
      <>
        {printAction}
        <div className="card">
          <h2>Findings</h2>
          <p style={{ color: 'var(--medium)' }}>No zones were checked; this is not proof the area is safe.</p>
        </div>
      </>
    )
  }
  
  const allFindings = []
  ;(audit.persons || []).forEach((person, pIdx) => {
    (person.findings || []).forEach((finding, fIdx) => {
      const findingKey = finding.id || `${person.id}:${finding.rule_id}:${fIdx}`
      allFindings.push({ person, finding, pIdx, fIdx, key: findingKey })
    })
  })
  
  // Filters
  let filteredFindings = allFindings.filter(({ person, finding }) => {
    if (filters?.severity && filters.severity !== 'all') {
      if (filters.severity === 'uncertain') {
        if (finding.kind !== 'uncertainty') return false
      } else {
        if (finding.kind === 'uncertainty') return false
        if (finding.severity !== filters.severity) return false
      }
    }
    if (filters?.zone && filters.zone !== 'all') {
      const zoneId = finding.zone_id !== undefined ? finding.zone_id : person.zone_id
      const zone = audit.zones?.find(z => z.id === zoneId)
      if ((zone?.name || 'No zone shown') !== filters.zone) return false
    }
    return true
  })
  
  // Summary
  const violationCount = allFindings.filter(f => f.finding.kind !== 'uncertainty').length
  const criticalCount = allFindings.filter(f => f.finding.severity === 'Critical' && f.finding.kind !== 'uncertainty').length
  const needsReviewCount = allFindings.filter(f => {
    const k = f.finding.id || `${f.person.id}:${f.finding.rule_id}:${f.fIdx}`
    const d = decisions?.[k] || (f.finding.review_state === 'needs_human_review' ? 'needs_human_review' : 'unreviewed')
    return d === 'needs_human_review'
  }).length
  
  if (allFindings.length === 0) {
    return (
      <>
        {printAction}
        <div className="card">
          <h2>Findings</h2>
          <p style={{ color: 'var(--success)' }} title="Not a safety clearance">No listed violations</p>
        </div>
      </>
    )
  }
  
  const zones = [...new Set(allFindings.map(({ person, finding }) => {
    const zoneId = finding.zone_id !== undefined ? finding.zone_id : person.zone_id
    const zone = audit.zones?.find(z => z.id === zoneId)
    return zone?.name || 'No zone shown'
  }))]
  
  return (
    <>
      {printAction}
      <div className="card findings-card">
        {showHeader && <h2>Findings ({allFindings.length})</h2>}
      <p className="findings-summary">
        {violationCount} findings <span aria-hidden="true">·</span> {criticalCount} Critical <span aria-hidden="true">·</span> {needsReviewCount} Needs review
      </p>
      <div className="findings-filters">
        <select value={filters?.severity || 'all'} onChange={(e) => setFilters && setFilters({...filters, severity: e.target.value})}>
          <option value="all">All Severities</option>
          <option value="Critical">Critical</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
          <option value="uncertain">Uncertain</option>
        </select>
        <select value={filters?.zone || 'all'} onChange={(e) => setFilters && setFilters({...filters, zone: e.target.value})}>
          <option value="all">All Zones</option>
          {zones.map(z => <option key={z} value={z}>{z}</option>)}
        </select>
      </div>
      <div className="findings-scroll">
        {filteredFindings.map(({ person, finding, pIdx, fIdx, key }) => {
          const zoneName = getZoneLabel(audit, person, finding)
          const isSelected = selectedId === person.id
          const isUncertainty = finding.kind === 'uncertainty'
          const isIllustrative = audit.trace_provenance === 'illustrative_fixture_only'
          const defaultReview = finding.review_state === 'needs_human_review' ? 'needs_human_review' : 'unreviewed'
          const currentReview = decisions?.[key] || defaultReview
          
          return (
            <div key={key} className={`finding-row ${isSelected ? 'selected' : ''}`}>
              <button
                type="button"
                onClick={() => onSelectPerson(person.id)}
                className="finding-person"
                aria-label={`Select Person ${pIdx + 1}`}
              >
                <span>Person {pIdx + 1}</span>
                <span className="finding-zone">{zoneName}</span>
              </button>
              
              <div className="finding-ppe">
                <span>Hard hat: <strong>{getPPELabel(person.helmet)}</strong></span>
                <span>Vest: <strong>{getPPELabel(person.vest)}</strong></span>
              </div>
              
              <div className="finding-meta">
                {isUncertainty ? (
                  <span className="uncertainty-badge" title="Needs human check">Uncertain</span>
                ) : (
                  <SeverityBadge severity={finding.severity} />
                )}
                <code className="rule-id">{finding.rule_id}</code>
              </div>
              
              <p className="finding-message">{finding.message}</p>
              
              <fieldset className="review">
                <legend className="sr-only">Review decision for {finding.rule_id}</legend>
                {['unreviewed', 'reviewed', 'needs_human_review'].map(v => (
                  <label key={v}>
                    <input 
                      type="radio" 
                      name={`review-${key}`} 
                      value={v}
                      checked={currentReview === v} 
                      onChange={() => setDecisions && setDecisions({...decisions, [key]: v})} 
                    />
                    <span>{v === 'needs_human_review' ? 'Needs review' : v === 'reviewed' ? 'Reviewed' : 'Unreviewed'}</span>
                  </label>
                ))}
              </fieldset>
              
              {finding.recheck_trace && finding.recheck_trace.length > 0 && (
                <div className="finding-recheck">
                  <button
                    type="button"
                    onClick={() => toggleExpand(key)}
                    className="btn btn-ghost recheck-btn"
                  >
                    {expanded[key] ? 'Hide' : 'Show'} {isIllustrative ? 'Illustrative (fixture), not a real re-check' : 'How was this checked?'}
                  </button>
                  {expanded[key] && (
                    <ul>
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
      <footer style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
        schema {audit.schema_version} / rules {audit.ruleset_version}
      </footer>
      </div>
    </>
  )
}
