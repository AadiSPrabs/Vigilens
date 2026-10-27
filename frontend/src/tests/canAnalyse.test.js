import { describe, it, expect } from 'vitest'
import { canAnalyse } from '../lib/canAnalyse'

describe('canAnalyse', () => {
  it('returns false if image missing', () => {
    expect(canAnalyse({ image: null, zones: [{id:'z1',points:[{x:0,y:0},{x:1,y:0},{x:0,y:1}]}], runWithoutZones: false, sample: null })).toBe(false)
  })

  it('returns false if zones empty and not runWithoutZones', () => {
    expect(canAnalyse({ image: {}, zones: [], runWithoutZones: false, sample: null })).toBe(false)
  })

  it('returns true if runWithoutZones true', () => {
    expect(canAnalyse({ image: {}, zones: [], runWithoutZones: true, sample: null })).toBe(true)
  })

  it('sample with edited zones vs preset via zonesEqual returns false', () => {
    const preset = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    const edited = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.16,y:0.3}] }]
    expect(canAnalyse({ image: {}, zones: edited, runWithoutZones: false, sample: { id: 's1', presetZones: preset } })).toBe(false)
  })

  it('sample with matching preset zones returns true', () => {
    const preset = [{ id: 'zone-1', hazard: true, points: [{x:0.1,y:0.2},{x:0.2,y:0.2},{x:0.15,y:0.3}] }]
    expect(canAnalyse({ image: {}, zones: preset, runWithoutZones: false, sample: { id: 's1', presetZones: preset } })).toBe(true)
  })
})
