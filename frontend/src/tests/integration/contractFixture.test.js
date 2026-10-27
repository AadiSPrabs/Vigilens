import { describe, it, expect } from 'vitest'
import { validateAudit } from '../../api/auditClient'
import contractAudit from '../../fixtures/contract/sample-audit-v0_2.json'

describe('Contract fixture', () => {
  it('validateAudit accepts contract fixture', () => {
    expect(validateAudit(contractAudit)).toBe(true)
  })

  it('handles uncertainty, worst_severity null, evidence url, zone_id null', () => {
    expect(contractAudit.persons[0].findings[0].kind).toBe('uncertainty')
    expect(contractAudit.persons[0].findings[0].severity).toBe(null)
    expect(contractAudit.persons[0].worst_severity).toBe(null)
    expect(contractAudit.evidence_image.url).toBeDefined()
    expect(contractAudit.persons[0].zone_id).toBe(null)
  })
})
