import React, { useState } from 'react'
import { getSeverityStyle } from '../lib/severity'

function getZoneName(audit, person, finding) {
  const zoneId = finding.zone_id !== undefined ? finding.zone_id : person.zone_id
  if (zoneId === null || zoneId === undefined) return 'No zone shown'
  const zone = audit.zones?.find(z => z.id === zoneId)
  return zone ? zone.name : 'Unknown zone'
}

function getSeverityRank(severity, kind) {
  if (kind === 'uncertainty') return 999
  if (severity === 'Critical') return 0
  if (severity === 'Medium') return 1
  if (severity === 'Low') return 2
  return 3 // unknown strings last
}

export default function HazardLog({ audit, selectedId, onSelectPerson, decisions }) {
  const [sortBy, setSortBy] = useState('severity')
  const [filterSeverity, setFilterSeverity] = useState('all')
  const [filterZone, setFilterZone] = useState('all')
  const [filterReview, setFilterReview] = useState('all')

  if (!audit || !Array.isArray(audit.persons)) return null

  const rows = []
  audit.persons.forEach((person, pIdx) => {
    (person.findings || []).forEach((finding, fIdx) => {
      const findingKey = finding.id || `${person.id}:${finding.rule_id}:${fIdx}`
      const zoneName = getZoneName(audit, person, finding)
      const review = decisions[findingKey] || (finding.review_state === 'needs_human_review' ? 'needs_human_review' : 'unreviewed')
      rows.push({
        key: findingKey,
        personId: person.id,
        personLabel: `Person ${pIdx + 1}`,
        zone: zoneName,
        message: finding.message,
        severity: finding.kind === 'uncertainty' ? 'Uncertain' : (finding.severity || 'Unknown'),
        kind: finding.kind,
        review,
        finding
      })
    })
  })

  // Filters
  let filtered = rows.filter(r => {
    if (filterSeverity !== 'all') {
      if (filterSeverity === 'uncertain' && r.kind !== 'uncertainty') return false
      else if (filterSeverity !== 'uncertain' && r.kind === 'uncertainty') return false
      else if (filterSeverity !== 'uncertain' && r.severity !== filterSeverity) return false
    }
    if (filterZone !== 'all' && r.zone !== filterZone) return false
    if (filterReview !== 'all' && r.review !== filterReview) return false
    return true
  })

  // Sort
  filtered.sort((a, b) => {
    if (sortBy === 'severity') {
      return getSeverityRank(a.severity === 'Uncertain' ? null : a.severity, a.kind) - getSeverityRank(b.severity === 'Uncertain' ? null : b.severity, b.kind)
    }
    return 0
  })

  const zones = [...new Set(rows.map(r => r.zone))]

  return (
    <div className="card">
      <h2>Hazard Log</h2>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
        <select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
          <option value="all">All Severities</option>
          <option value="Critical">Critical</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
          <option value="uncertain">Uncertain</option>
        </select>
        <select value={filterZone} onChange={(e) => setFilterZone(e.target.value)}>
          <option value="all">All Zones</option>
          {zones.map(z => <option key={z} value={z}>{z}</option>)}
        </select>
        <select value={filterReview} onChange={(e) => setFilterReview(e.target.value)}>
          <option value="all">All Reviews</option>
          <option value="unreviewed">Unreviewed</option>
          <option value="reviewed">Reviewed</option>
          <option value="needs_human_review">Needs human review</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="severity">Sort by Severity</option>
        </select>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Person</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Zone</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Finding</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Severity</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Review</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(row => (
              <tr 
                key={row.key}
                onClick={() => onSelectPerson(row.personId)}
                style={{ 
                  cursor: 'pointer',
                  background: selectedId === row.personId ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                  borderBottom: '1px solid var(--border)'
                }}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelectPerson(row.personId)
                  }
                }}
              >
                <td style={{ padding: '0.5rem' }}>{row.personLabel}</td>
                <td style={{ padding: '0.5rem' }}>{row.zone}</td>
                <td style={{ padding: '0.5rem', fontSize: '0.875rem' }}>{row.message}</td>
                <td style={{ padding: '0.5rem' }}>{row.kind === 'uncertainty' ? 'Uncertain' : row.severity}</td>
                <td style={{ padding: '0.5rem' }}>{row.review === 'needs_human_review' ? 'Needs human review' : row.review === 'reviewed' ? 'Reviewed' : 'Unreviewed'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
