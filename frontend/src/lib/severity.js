// PPE/Severity rules per requirements
// - PPE values: present, absent, unknown -> "Unclear - needs human check" (never converted)
// - Severity colors: Critical=red, Medium=amber, Low=blue-grey (not green)
// - Any other severity (including "High") -> neutral grey + raw text
// - Green is used only when findings empty AND helmet and vest both "present" (fully equipped person)
// - Person outline tinted by worst_severity if present else neutral; never use findings[0]
// - Uncertainty: kind:"uncertainty" with severity:null -> "Uncertain - needs human check", not violation/equipped status
//
// Colours live in styles.css as theme tokens. These helpers return token
// references so the same semantics re-theme live in Day and Night.

const NEUTRAL_STYLE = {
  color: 'var(--sev-neutral-stroke)',
  fill: 'var(--sev-neutral-fill)',
  stroke: 'var(--sev-neutral-stroke)'
}

const SEVERITY_STYLES = {
  Critical: {
    color: 'var(--sev-critical-stroke)',
    fill: 'var(--sev-critical-fill)',
    stroke: 'var(--sev-critical-stroke)'
  },
  Medium: {
    color: 'var(--sev-medium-stroke)',
    fill: 'var(--sev-medium-fill)',
    stroke: 'var(--sev-medium-stroke)'
  },
  Low: {
    color: 'var(--sev-low-stroke)',
    fill: 'var(--sev-low-fill)',
    stroke: 'var(--sev-low-stroke)'
  }
}

export function getSeverityStyle(severity) {
  return SEVERITY_STYLES[severity] || NEUTRAL_STYLE
}

export function isPersonFullyEquipped(person) {
  if (!person) return false
  if (!person.findings || person.findings.length > 0) return false
  // Has uncertainty findings - not fully equipped
  if (person.helmet === 'present' && person.vest === 'present') return true
  return false
}

export function getPersonColor(person) {
  if (!person) return NEUTRAL_STYLE
  // Check for uncertainty
  if (Array.isArray(person.findings)) {
    for (const f of person.findings) {
      if (f.kind === 'uncertainty') {
        return NEUTRAL_STYLE
      }
    }
  }
  if (isPersonFullyEquipped(person)) {
    return {
      color: 'var(--sev-no-listed-stroke)',
      fill: 'var(--sev-no-listed-fill)',
      stroke: 'var(--sev-no-listed-stroke)'
    }
  }
  if (person.worst_severity) {
    return getSeverityStyle(person.worst_severity)
  }
  // neutral
  return NEUTRAL_STYLE
}
