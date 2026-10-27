// Pure severity helpers
// Critical = red, Medium = amber, Low = green
// ANY other string (including "High") renders neutral grey and shows the raw string as text
// Severity is always colour AND text

export function getSeverityStyle(severity) {
  const s = typeof severity === 'string' ? severity : ''
  if (s === 'Critical') {
    return { color: '#dc2626', bg: '#fee2e2', label: 'Critical', neutral: false }
  }
  if (s === 'Medium') {
    return { color: '#d97706', bg: '#fef3c7', label: 'Medium', neutral: false }
  }
  if (s === 'Low') {
    return { color: '#16a34a', bg: '#dcfce7', label: 'Low', neutral: false }
  }
  // Any other string (including "High") -> neutral grey, show raw string
  return { color: '#4b5563', bg: '#f3f4f6', label: s || 'Unknown', neutral: true }
}
