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

function getPolygonBounds(points) {
  if (!Array.isArray(points) || points.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  points.forEach(point => {
    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') return
    minX = Math.min(minX, point.x)
    minY = Math.min(minY, point.y)
    maxX = Math.max(maxX, point.x)
    maxY = Math.max(maxY, point.y)
  })
  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null
  }
  return { minX, minY, maxX, maxY }
}

function getReticleGeometry(bounds) {
  if (!bounds) return null
  const padding = 0.018
  const x0 = Math.max(0, bounds.minX - padding)
  const y0 = Math.max(0, bounds.minY - padding)
  const x1 = Math.min(1, bounds.maxX + padding)
  const y1 = Math.min(1, bounds.maxY + padding)
  const width = x1 - x0
  const height = y1 - y0
  const corner = Math.min(0.04, Math.max(0.014, Math.min(width, height) * 0.35))
  const tick = Math.min(0.012, Math.max(0.006, Math.min(width, height) * 0.12))
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2

  return {
    corners: [
      `M ${x0} ${y0 + corner} L ${x0} ${y0} L ${x0 + corner} ${y0}`,
      `M ${x1 - corner} ${y0} L ${x1} ${y0} L ${x1} ${y0 + corner}`,
      `M ${x0} ${y1 - corner} L ${x0} ${y1} L ${x0 + corner} ${y1}`,
      `M ${x1 - corner} ${y1} L ${x1} ${y1} L ${x1} ${y1 - corner}`
    ],
    ticks: [
      `M ${cx - tick} ${y0} H ${cx + tick} M ${cx} ${y0 - tick} V ${y0 + tick}`,
      `M ${cx - tick} ${y1} H ${cx + tick} M ${cx} ${y1 - tick} V ${y1 + tick}`,
      `M ${x0 - tick} ${cy} H ${x0 + tick} M ${x0} ${cy - tick} V ${cy + tick}`,
      `M ${x1 - tick} ${cy} H ${x1 + tick} M ${x1} ${cy - tick} V ${cy + tick}`
    ]
  }
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

  const selectedPerson = selectedId !== null && selectedId !== undefined
    ? (audit.persons || []).find(person => person.id === selectedId)
    : null
  const reticle = getReticleGeometry(getPolygonBounds(selectedPerson?.polygon))
  
  return (
    <div className="card">
      <h2>Audit Overlay</h2>
      <div className="canvas-frame">
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
          <defs>
            <pattern
              id="hazard-pattern"
              patternUnits="userSpaceOnUse"
              width="0.04"
              height="0.04"
              patternTransform="rotate(45)"
            >
              <rect width="0.04" height="0.04" fill="#000000" opacity="0.12" />
              <line x1="0" y1="0" x2="0" y2="0.04" stroke="#f59e0b" strokeWidth="0.002" opacity="0.25" />
              <line x1="0.02" y1="0" x2="0.02" y2="0.04" stroke="#000000" strokeWidth="0.002" opacity="0.25" />
            </pattern>
            <pattern
              id="restricted-pattern"
              patternUnits="userSpaceOnUse"
              width="0.04"
              height="0.04"
              patternTransform="rotate(45)"
            >
              <rect width="0.04" height="0.04" fill="#000000" opacity="0.1" />
              <line x1="0" y1="0" x2="0" y2="0.04" stroke="#94a3b8" strokeWidth="0.002" opacity="0.2" />
              <line x1="0.02" y1="0" x2="0.02" y2="0.04" stroke="#000000" strokeWidth="0.002" opacity="0.2" />
            </pattern>
          </defs>
          {(audit.zones || []).map(zone => (
            <polygon
              key={zone.id}
              className={`zone-region ${zone.hazard ? 'hazard' : 'restricted'}`}
              points={zone.points.map(p => `${p.x},${p.y}`).join(' ')}
              fill={zone.hazard ? 'url(#hazard-pattern)' : 'url(#restricted-pattern)'}
              stroke={zone.hazard ? '#ff334b' : '#94a3b8'}
              strokeWidth="0.002"
              strokeLinejoin="round"
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
          {reticle && (
            <g className="hud-reticle" aria-hidden="true">
              {reticle.corners.map((path, index) => (
                <path key={`corner-${index}`} className="reticle-corner" d={path} />
              ))}
              {reticle.ticks.map((path, index) => (
                <path key={`tick-${index}`} className="reticle-tick" d={path} />
              ))}
            </g>
          )}
        </svg>
        </div>
      </div>
    </div>
  )
}
