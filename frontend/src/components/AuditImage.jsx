import React, { useRef } from 'react'
import { getSeverityStyle } from '../lib/severity'

export default function AuditImage({ imageSrc, audit, selectedId, onSelectPerson }) {
  const imgRef = useRef(null)
  
  const getPersonColor = (person) => {
    if (person.worst_severity) {
      const style = getSeverityStyle(person.worst_severity)
      return style.neutral ? '#64748b' : style.color
    }
    return '#64748b' // neutral
  }
  
  const getPersonLabel = (person, idx) => {
    const findingsCount = person.findings?.length || 0
    const zoneName = audit.zones?.find(z => z.id === person.zone_id)?.name || 'outside zones'
    return `Person ${idx + 1}, ${findingsCount} findings, in ${zoneName}`
  }
  
  return (
    <div className="card">
      <h2>Audit Overlay</h2>
      <div className="zone-canvas-wrapper">
        <img 
          ref={imgRef}
          src={imageSrc} 
          alt="Site image with audit overlays"
        />
        <svg 
          className="zone-svg"
          viewBox="0 0 1 1" 
          preserveAspectRatio="none"
          role="img"
          aria-label="Audit overlays"
        >
          {/* Zones - dashed blue */}
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
          {/* Persons */}
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
