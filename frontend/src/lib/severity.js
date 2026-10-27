// Pure severity helpers - v0.2
// Critical = red, Medium = amber, Low = blue-grey (NOT green)
// Any other string = neutral grey + raw text
// Green is used only for an explicit compliant person: findings empty AND helmet and vest both "present"

export function getSeverityStyle(severity) {
  const s = typeof severity === 'string' ? severity : ''
  if (s === 'Critical') {
    return { color: '#dc2626', bg: '#fee2e2', label: 'Critical', neutral: false }
  }
  if (s === 'Medium') {
    return { color: '#d97706', bg: '#fef3c7', label: 'Medium', neutral: false }
  }
  if (s === 'Low') {
    return { color: '#64748b', bg: '#e2e8f0', label: 'Low', neutral: false }
  }
  // Any other string = neutral grey, show raw string
  return { color: '#4b5563', bg: '#f3f4f6', label: s || 'Unknown', neutral: true }
}

export function isPersonCompliant(person) {
  if (!person) return false
  const findings = person.findings || []
  // Has uncertainty findings - not compliant
  const hasUncertainty = findings.some(f => f.kind === 'uncertainty')
  if (hasUncertainty) return false
  if (findings.length > 0) return false
  if (person.helmet === 'present' && person.vest === 'present') return true
  return false
}
