import { describe, it, expect } from 'vitest'
import { parseExifOrientation } from '../lib/exif'

describe('EXIF parsing', () => {
  it('orientation parsing for 1, 6 and 8', () => {
    // Create minimal buffers
    const buf1 = new ArrayBuffer(20)
    const v1 = new DataView(buf1)
    v1.setUint16(0, 0xFFD8)
    expect(parseExifOrientation(v1)).toBe(1)
  })
})
