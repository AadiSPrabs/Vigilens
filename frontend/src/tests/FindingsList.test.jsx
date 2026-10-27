import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FindingsList from '../components/FindingsList'

describe('FindingsList', () => {
  it('unknown never shown as absent', () => {
    const audit = {
      zones: [{id: 'z1', name: 'Zone1'}],
      persons: [{
        id: 'p1',
        helmet: 'unknown',
        vest: 'present',
        zone_id: 'z1',
        findings: [{ rule_id: 'R1', severity: 'Low', message: 'test', review_state: 'auto', recheck_trace: [] }]
      }]
    }
    render(<FindingsList audit={audit} selectedId={null} onSelectPerson={() => {}} />)
    expect(screen.getByText(/Unclear - needs human check/)).toBeInTheDocument()
    expect(screen.queryByText(/^Absent$/)).not.toBeInTheDocument()
  })

  it('selecting a finding selects its polygon', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const audit = {
      zones: [{id: 'z1', name: 'Zone1'}],
      persons: [{
        id: 'p1',
        helmet: 'present',
        vest: 'present',
        zone_id: 'z1',
        findings: [{ rule_id: 'R1', severity: 'Low', message: 'test', review_state: 'auto', recheck_trace: [] }]
      }]
    }
    render(<FindingsList audit={audit} selectedId={null} onSelectPerson={onSelect} />)
    const btn = screen.getByLabelText(/Select Person 1/)
    await user.click(btn)
    expect(onSelect).toHaveBeenCalledWith('p1')
  })
})
