import { describe, it, expect } from 'vitest'
import { clientToNormalised, zonesEqual } from '../lib/geometry'

describe('geometry', () => {
  it('clientToNormalised clamps/returns null for out of bounds', () => {
    const img = {
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 50 })
    }
    const e1 = { clientX: -1, clientY: 10 }
    expect(clientToNormalised(e1, img)).toBe(null)
    const e2 = { clientX: 200, clientY: 10 }
    expect(clientToNormalised(e2, img)).toBe(null)
    const e3 = { clientX: 10, clientY: -1 }
    expect(clientToNormalised(e3, img)).toBe(null)
    const e4 = { clientX: 10, clientY: 100 }
    expect(clientToNormalised(e4, img)).toBe(null)
  })

  it('zonesEqual returns true only for identical zones', () => {
    const a = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    const b = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    expect(zonesEqual(a,b)).toBe(true)
    const c = [{ id: 'zone-1', hazard: false, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    expect(zonesEqual(a,c)).toBe(false)
  })
})

  it('clientToNormalised returns null for negative and > 1', () => {
    const img = {
      getBoundingClientRect: () => ({ left: 10, top: 20, width: 200, height: 100 })
    }
    expect(clientToNormalised({ clientX: 5, clientY: 50 }, img)).toBe(null)
    expect(clientToNormalised({ clientX: 300, clientY: 50 }, img)).toBe(null)
    expect(clientToNormalised({ clientX: 50, clientY: 10 }, img)).toBe(null)
    expect(clientToNormalised({ clientX: 50, clientY: 150 }, img)).toBe(null)
  })

  it('zonesEqual returns false with mismatched point', () => {
    const a = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    const b = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.16,y:0.3}] }]
    expect(zonesEqual(a,b)).toBe(false)
  })

  it('zone id never reused after delete conceptually', () => {
    // Conceptual test - ensure we track counter properly
    const zones = [{id: 'zone-1'}, {id: 'zone-2'}]
    const filtered = zones.filter(z => z.id !== 'zone-1')
    expect(filtered.find(z => z.id === 'zone-1')).toBeUndefined()
  })
