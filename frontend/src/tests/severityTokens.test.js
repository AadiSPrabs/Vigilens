import { describe, it, expect } from 'vitest'
import { getSeverityStyle } from '../lib/severity'

describe('severity token mapping', () => {
  const expected = [
    ['Critical', '--sev-critical-'],
    ['Medium', '--sev-medium-'],
    ['Low', '--sev-low-']
  ]

  it.each(expected)('%s returns its --sev-* tokens', (severity, tokenPrefix) => {
    const style = getSeverityStyle(severity)
    expect(style.color).toBe(`var(${tokenPrefix}stroke)`)
    expect(style.stroke).toBe(`var(${tokenPrefix}stroke)`)
    expect(style.fill).toBe(`var(${tokenPrefix}fill)`)
  })

  it('never maps a violation severity to the green no-listed token', () => {
    for (const [severity] of expected) {
      const style = getSeverityStyle(severity)
      expect(style.color).not.toContain('--sev-no-listed')
      expect(style.stroke).not.toContain('--sev-no-listed')
      expect(style.fill).not.toContain('--sev-no-listed')
      expect(style.color).not.toBe('#16a34a')
    }
  })
})
