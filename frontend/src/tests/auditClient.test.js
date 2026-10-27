import { describe, it, expect } from 'vitest'
import { validateAudit } from '../api/auditClient'

describe('validateAudit', () => {
  it('accepts valid audit', () => {
    const audit = {
      audit_id: 'a1',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [{ id: 'z1', name: 'Z', hazard: true, points: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}] }],
      persons: [{ id: 'p1', polygon: [{x:0.3,y:0.3},{x:0.4,y:0.3},{x:0.35,y:0.4}], helmet: 'present', vest: 'absent', zone_id: 'z1', findings: [] }]
    }
    expect(validateAudit(audit)).toBe(true)
  })

  it('rejects out of range coordinate', () => {
    const audit = {
      audit_id: 'a1',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [{ id: 'z1', name: 'Z', hazard: true, points: [{x:1.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}] }],
      persons: []
    }
    expect(() => validateAudit(audit)).toThrow()
  })

  it('rejects bad helmet value', () => {
    const audit = {
      audit_id: 'a1',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [],
      persons: [{ id: 'p1', polygon: [{x:0.3,y:0.3},{x:0.4,y:0.3},{x:0.35,y:0.4}], helmet: 'yes', vest: 'present' }]
    }
    expect(() => validateAudit(audit)).toThrow()
  })

  it('rejects missing fields', () => {
    expect(() => validateAudit({})).toThrow()
    expect(() => validateAudit({ audit_id: 'a1' })).toThrow()
  })
})
