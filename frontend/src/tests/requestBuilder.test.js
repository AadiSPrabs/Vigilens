import { describe, it, expect } from 'vitest'
import { buildAuditRequest } from '../lib/requestBuilder'

describe('request builder', () => {
  it('request has header concept, zones have exactly 4 keys, extra fields stripped', () => {
    const zones = [{ id: 'z1', name: 'Z', hazard: true, points: [{ x: 0.1, y: 0.2, extra: 1 }], extraField: 'bad' }]
    const file = new File(['x'], 'test.png', { type: 'image/png' })
    const result = buildAuditRequest(file, zones)
    expect(result.formData).toBeInstanceOf(FormData)
    expect(result.idempotencyKey).toBeDefined()
    const zoneStr = result.formData.get('zones')
    const parsed = JSON.parse(zoneStr)
    expect(Object.keys(parsed[0]).sort()).toEqual(['hazard', 'id', 'name', 'points'])
    expect(Object.keys(parsed[0].points[0])).toEqual(['x', 'y'])
  })
})
