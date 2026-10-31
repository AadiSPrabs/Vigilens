import React from 'react'
import { SeverityShape } from './Icons'

const KNOWN_SEVERITIES = ['Critical', 'Medium', 'Low']

export default function SeverityBadge({ severity, kind }) {
  const isUncertain = kind === 'uncertainty' || severity === 'Uncertain'
  const isKnown = KNOWN_SEVERITIES.includes(severity)
  const label = isUncertain ? 'Uncertain' : (isKnown ? severity : (severity || 'Unknown'))
  const variant = isUncertain ? 'uncertain' : (isKnown ? label.toLowerCase() : 'unknown')
  return (
    <span className={`severity-badge severity-${variant}`} aria-label={`Severity: ${label}`}>
      <SeverityShape variant={variant} size={12} />
      <span>{label}</span>
    </span>
  )
}
