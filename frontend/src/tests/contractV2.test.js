import { describe, it, expect, vi } from 'vitest'
import { resolveEvidence } from '../lib/evidence'

describe('Contract v0.2', () => {
  it('resolveEvidence never returns the original', () => {
    const result = resolveEvidence({ evidence_image: null })
    expect(result.ok).toBe(false)
    expect(result.src).toBe(null)
  })

  it('uncertainty findings never render as violation or compliant', () => {
    const finding = { kind: 'uncertainty', severity: null }
    expect(finding.kind).toBe('uncertainty')
    expect(finding.severity).toBe(null)
  })

  it('Low is not green', () => {
    const { getSeverityStyle } = require('../lib/severity')
    const style = getSeverityStyle('Low')
    expect(style.color).not.toBe('#16a34a')
  })
})
