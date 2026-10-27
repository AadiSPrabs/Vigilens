import { describe, it, expect } from 'vitest'
import { validateAudit } from '../../api/auditClient'
import { polygonArea, selfIntersects } from '../../lib/geometry'
import { preCheckFile } from '../../lib/validation'

describe('v2c tests', () => {
  it('boolean coord rejected', () => {
    const audit = {
      audit_id: 'a1',
      image: { id: 'i1', width: 100, height: 100 },
      zones: [{ id: 'z1', name: 'Z', hazard: false, points: [{x: true, y: 0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}] }],
      persons: []
    }
    expect(() => validateAudit(audit)).toThrow()
  })

  it('zero-area polygon rejected', () => {
    expect(polygonArea([{x:0,y:0},{x:1,y:0},{x:0.5,y:0}])).toBe(0)
  })

  it('bowtie self-intersecting rejected', () => {
    const bowtie = [{x:0,y:0},{x:1,y:1},{x:1,y:0},{x:0,y:1}]
    expect(selfIntersects(bowtie)).toBe(true)
  })
})
