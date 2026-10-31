import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FindingsList from '../components/FindingsList'

describe('Phase 6', () => {
  beforeEach(() => {
    window.print = vi.fn()
  })

  it('print button calls window.print when audit loaded', async () => {
    const user = userEvent.setup()
    const audit = {
      schema_version: '0.2-local-draft',
      ruleset_version: '1',
      audit_id: 'a1',
      image: { id: 'i1', width: 100, height: 100 },
      zones: [{ id: 'z1', name: 'Zone1', points: [{x:0,y:0},{x:1,y:0},{x:0.5,y:1}] }],
      persons: [{
        id: 'p1',
        polygon: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}],
        helmet: 'present',
        vest: 'absent',
        zone_id: 'z1',
        findings: [{ id: 'f1', rule_id: 'R1', severity: 'Critical', kind: 'violation', message: 'test', review_state: 'auto' }]
      }]
    }
    render(<FindingsList audit={audit} selectedId={null} onSelectPerson={() => {}} decisions={{}} setDecisions={() => {}} filters={{severity:'all', zone:'all'}} setFilters={() => {}} />)
    const btn = screen.getByRole('button', { name: /Print/i })
    await user.click(btn)
    expect(window.print).toHaveBeenCalled()
  })

  it('print button hidden when no audit', () => {
    render(<FindingsList audit={null} selectedId={null} onSelectPerson={() => {}} decisions={{}} setDecisions={() => {}} filters={{severity:'all', zone:'all'}} setFilters={() => {}} />)
    expect(screen.queryByRole('button', { name: /Print/i })).not.toBeInTheDocument()
  })
})
