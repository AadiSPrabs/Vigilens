// PPE/Severity rules per requirements
// - PPE values: present, absent, unknown -> "Unclear - needs human check" (never converted)
// - Severity colors: Critical=red, Medium=amber, Low=blue-grey (not green)
// - Any other severity (including "High") -> neutral grey + raw text
// - Green is used only when findings empty AND helmet and vest both "present" (fully equipped person)
// - Person outline tinted by worst_severity if present else neutral; never use findings[0]
// - Uncertainty: kind:"uncertainty" with severity:null -> "Uncertain - needs human check", not violation/equipped status

export function getSeverityStyle(severity) {
  if (severity === 'Critical') {
    return { color: '#dc2626', fill: 'rgba(220,38,38,0.1)', stroke: '#dc2626' }
  }
  if (severity === 'Medium') {
    return { color: '#f59e0b', fill: 'rgba(245,158,11,0.1)', stroke: '#f59e0b' }
  }
  if (severity === 'Low') {
    return { color: '#64748b', fill: 'rgba(100,116,139,0.1)', stroke: '#64748b' }
  }
  return { color: '#6b7280', fill: 'rgba(107,114,128,0.05)', stroke: '#6b7280' }
}

export function isPersonFullyEquipped(person) {
  if (!person) return false
  if (!person.findings || person.findings.length > 0) return false
  // Has uncertainty findings - not fully equipped
  if (person.helmet === 'present' && person.vest === 'present') return true
  return false
}

export function getPersonColor(person) {
  if (!person) return { color: '#6b7280', fill: 'rgba(107,114,128,0.05)', stroke: '#6b7280' }
  // Check for uncertainty
  if (Array.isArray(person.findings)) {
    for (const f of person.findings) {
      if (f.kind === 'uncertainty') {
        return { color: '#6b7280', fill: 'rgba(107,114,128,0.05)', stroke: '#6b7280' }
      }
    }
  }
  if (isPersonFullyEquipped(person)) {
    return { color: '#16a34a', fill: 'rgba(22,163,74,0.1)', stroke: '#16a34a' }
  }
  if (person.worst_severity) {
    return getSeverityStyle(person.worst_severity)
  }
  // neutral
  return { color: '#6b7280', fill: 'rgba(107,114,128,0.05)', stroke: '#6b7280' }
}
