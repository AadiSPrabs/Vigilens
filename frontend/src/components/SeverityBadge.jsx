import React from 'react'
import { getSeverityStyle } from '../lib/severity'

export default function SeverityBadge({ severity }) {
  const style = getSeverityStyle(severity)
  return (
    <span 
      style={{ 
        color: style.color, 
        background: style.bg, 
        padding: '0.25rem 0.5rem', 
        borderRadius: '4px',
        fontSize: '0.875rem',
        fontWeight: '600'
      }}
      aria-label={`Severity: ${style.label}`}
    >
      {style.label}
    </span>
  )
}
