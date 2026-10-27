import React, { useState } from 'react'
import { getSeverityStyle, isPersonCompliant } from '../lib/severity'
import { resolveEvidence } from '../lib/evidence'

export default function AuditImage({ audit, selectedId, onSelectPerson }) {
  const [imgError, setImgError] = useState(false)
  const [imgMismatch, setImgMismatch] = useState(false)
  const evidence = resolveEvidence(audit)
  
  const handleImageLoad = (e) => {
    const img = e.target
    const auditW = audit?.image?.width
    const auditH = audit?.image?.height
    if (auditW && auditH && img.naturalWidth && img.naturalHeight) {
      const auditRatio = auditW / auditH
      const imgRatio = img.naturalWidth / img.naturalHeight
      if (Math.abs(auditRatio - imgRatio) / auditRatio > 0.01) {
        setImgMismatch(true)
      }
    }
  }
  
  const getPersonColor = (person) => {
    if (isPersonCompliant(person)) {
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
    const zoneId = person.findings?.[0]?.zone_id !== undefined ? person.findings[0].zone_id : person.zone_id
    let zoneName
    if (zoneId === null) {
      zoneName = 'No zone shown'
    } else if (zoneId) {
      zoneName = audit.zones?.find(z => z.id === zoneId)?.name || 'Unknown zone'
    } else {
      zoneName = 'No zone shown'
    }
    return `Person ${idx + 1}, ${findingsCount} findings, in ${zoneName}`
  }
  
  if (!evidence.ok || imgError || imgMismatch) {
    return (
      <div className="card">
        <h2>Audit Overlay</h2>
        <p style={{ color: 'var(--critical)' }}>
          {imgMismatch ? 'Evidence image does not match the audited image' : 'Masked evidence unavailable'}
        </p>
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
          onLoad={handleImageLoad}
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
