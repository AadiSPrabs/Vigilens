import React from 'react'

const KNOWN_SEVERITIES = ['Critical', 'Medium', 'Low']

export default function SeverityBadge({ severity }) {
  const label = KNOWN_SEVERITIES.includes(severity) ? severity : (severity || 'Unknown')
  const variant = KNOWN_SEVERITIES.includes(severity) ? label.toLowerCase() : 'unknown'
  return (
    <span className={`severity-badge severity-${variant}`} aria-label={`Severity: ${label}`}>
      {label}
    </span>
  )
}
