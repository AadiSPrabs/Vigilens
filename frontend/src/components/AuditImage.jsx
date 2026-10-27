import React, { useState } from 'react'
import { getSeverityStyle, isPersonFullyEquipped } from '../lib/severity'
import { resolveEvidence } from '../lib/evidence'

function getZoneLabelForPerson(audit, person) {
  const zoneId = person.findings?.[0]?.zone_id !== undefined ? person.findings[0].zone_id : person.zone_id
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

export default function AuditImage({ audit, selectedId, onSelectPerson, uploadedNaturalSize, evidenceExportAllowed }) {
  const [imgError, setImgError] = useState(false)
  const evidence = resolveEvidence(audit)
  
  // Check image dimensions match
  if (uploadedNaturalSize && audit.image) {
    if (uploadedNaturalSize.width !== audit.image.width || uploadedNaturalSize.height !== audit.image.height) {
      return (
        <div className="card">
          <h2>Audit Overlay</h2>
          <p style={{ color: 'var(--critical)' }}>Response does not match the uploaded image</p>
        </div>
      )
    }
  }
  
  const getPersonColor = (person) => {
    if (isPersonFullyEquipped(person)) {
      return '#16a34a'
    }
    const findings = person.findings || []
    const hasUncertainty = findings.some(f => f.kind === 'uncertainty')
    if (hasUncertainty && findings.every(f => f.kind === 'uncertainty')) {
      return '#64748b'
    }
    if (person.worst_severity) {
      const style = getSeverityStyle(person.worst_severity)
      return style.neutral ? '#64748b' : style.color
    }
    return '#64748b'
  }
  
  const getPersonLabel = (person, idx) => {
    const findingsCount = (person.findings || []).length
    const zoneName = getZoneLabelForPerson(audit, person)
    return `Person ${idx + 1}, ${findingsCount} findings, in ${zoneName}`
  }
  
  if (!evidence.ok || imgError) {
    return (
      <div className="card">
        <h2>Audit Overlay</h2>
        <p style={{ color: 'var(--critical)' }}>Masked evidence unavailable</p>
      </div>
    )
  }
  
  return (
    <div className="card">
      <h2>Audit Overlay</h2>
      <div className="zone-canvas-wrapper">
        <img 
          src={evidence.src} 
          alt="Site image with audit overlays"
          onError={() => setImgError(true)}
        />
        <svg 
          className="zone-svg"
          viewBox="0 0 1 1" 
          preserveAspectRatio="none"
          role="img"
          aria-label="Audit overlays"
        >
          {(audit.zones || []).map(zone => (
            <polygon
              key={zone.id}
              points={zone.points.map(p => `${p.x},${p.y}`).join(' ')}
              fill={zone.hazard ? 'rgba(220, 38, 38, 0.1)' : 'rgba(59, 130, 246, 0.1)'}
              stroke={zone.hazard ? '#dc2626' : '#3b82f6'}
              strokeWidth="0.002"
              strokeDasharray="0.01,0.005"
            />
          ))}
          {(audit.persons || []).map((person, idx) => {
            const isSelected = selectedId === person.id
            const color = getPersonColor(person)
            return (
              <polygon
                key={person.id}
                className="zone-polygon"
                points={person.polygon.map(p => `${p.x},${p.y}`).join(' ')}
                fill={isSelected ? color + '40' : color + '20'}
                stroke={color}
                strokeWidth={isSelected ? '0.004' : '0.002'}
                tabIndex={0}
                role="button"
                aria-label={getPersonLabel(person, idx)}
                onClick={() => onSelectPerson(person.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelectPerson(person.id)
                  }
                }}
                style={{ cursor: 'pointer', pointerEvents: 'all' }}
              />
            )
          })}
        </svg>
      </div>
    </div>
  )
}
