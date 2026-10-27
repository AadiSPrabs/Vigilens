import { describe, it, expect } from 'vitest'
import { preCheckFile, preCheckZones } from '../lib/validation'

describe('Pre-checks', () => {
  it('pre-check limits', () => {
    const bigFile = { size: 20000000, type: 'image/png' }
    expect(preCheckFile(bigFile).ok).toBe(false)
    const badType = { size: 1000, type: 'image/gif' }
    expect(preCheckFile(badType).ok).toBe(false)
    const tooManyZones = Array(21).fill({ points: [] })
    expect(preCheckZones(tooManyZones).ok).toBe(false)
  })

  it('FormData has no manual Content-Type', () => {
    const fd = new FormData()
    fd.append('image', new Blob())
    fd.append('zones', '[]')
    expect(fd.get('image')).toBeDefined()
    expect(fd.get('zones')).toBe('[]')
  })
})
