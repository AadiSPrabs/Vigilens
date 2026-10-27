import { describe, it, expect } from 'vitest'
import { validateAudit } from '../api/auditClient'
import contractZones from '../fixtures/contract/contract-zones.json'

describe('Phase 2e', () => {
  it('contract-zones.json matches order and numbers and passes validator shape', () => {
    expect(contractZones.length).toBe(2)
    expect(contractZones[0].id).toBe('zone-1')
    expect(contractZones[0].name).toBe('Crane Zone')
    expect(contractZones[0].hazard).toBe(true)
    expect(contractZones[1].id).toBe('zone-2')
    expect(contractZones[1].name).toBe('Restricted Area')
    expect(contractZones[1].hazard).toBe(true)
    expect(Object.keys(contractZones[0])).toEqual(['id', 'name', 'hazard', 'points'])
    expect(Object.keys(contractZones[0].points[0])).toEqual(['x', 'y'])
  })

  it('missing or duplicate finding ids rejected in backend mode', () => {
    const audit1 = {
      schema_version: '0.2',
      audit_id: 'a1',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [{ id: 'z1', name: 'Z', hazard: false, points: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}] }],
      persons: [{ id: 'p1', polygon: [{x:0.3,y:0.3},{x:0.4,y:0.3},{x:0.35,y:0.4}], helmet: 'present', vest: 'present', findings: [{ rule_id: 'R1', severity: 'Low', kind: 'violation' }] }]
    }
    expect(() => validateAudit(audit1, { mode: 'backend' })).toThrow()
    const audit2 = {
      schema_version: '0.2',
      audit_id: 'a2',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [{ id: 'z1', name: 'Z', hazard: false, points: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}] }],
      persons: [{ id: 'p1', polygon: [{x:0.3,y:0.3},{x:0.4,y:0.3},{x:0.35,y:0.4}], helmet: 'present', vest: 'present', findings: [{ id: 'f1', rule_id: 'R1', severity: 'Low', kind: 'violation' }, { id: 'f1', rule_id: 'R2', severity: 'Low', kind: 'violation' }] }]
    }
    expect(() => validateAudit(audit2, { mode: 'backend' })).toThrow()
  })

  it('unknown schema_version rejected', () => {
    const audit = {
      schema_version: '0.3',
      audit_id: 'a1',
      image: { id: 'i1', width: 1280, height: 720 },
      zones: [],
      persons: []
    }
    expect(() => validateAudit(audit)).toThrow('Unsupported schema version')
  })
})
