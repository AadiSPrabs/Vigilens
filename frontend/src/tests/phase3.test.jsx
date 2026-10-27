import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FindingsList from '../components/FindingsList'

describe('Phase 3', () => {
  it('review decisions state', async () => {
    const user = userEvent.setup()
    const setDecisions = vi.fn()
    const audit = {
      schema_version: '0.2',
      ruleset_version: '1',
      zones: [{id: 'z1', name: 'Zone1'}],
      persons: [{
        id: 'p1',
        helmet: 'present',
        vest: 'present',
        zone_id: 'z1',
        findings: [{ id: 'f1', rule_id: 'R1', severity: 'Low', kind: 'violation', message: 'test', review_state: 'auto' }]
      }]
    }
    render(<FindingsList audit={audit} selectedId={null} onSelectPerson={() => {}} decisions={{}} setDecisions={setDecisions} filters={{severity:'all', zone:'all'}} setFilters={() => {}} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.length).toBe(3)
  })

  it('filters', () => {
    const audit = {
      schema_version: '0.2',
      ruleset_version: '1',
      zones: [{id: 'z1', name: 'Zone1'}],
      persons: [{
        id: 'p1',
        helmet: 'present',
        vest: 'present',
        zone_id: 'z1',
        findings: [{ id: 'f1', rule_id: 'R1', severity: 'Critical', kind: 'violation', message: 'test', review_state: 'auto' }]
      }]
    }
    render(<FindingsList audit={audit} selectedId={null} onSelectPerson={() => {}} decisions={{}} setDecisions={() => {}} filters={{severity:'Critical', zone:'all'}} setFilters={() => {}} />)
    expect(screen.getByText('test')).toBeInTheDocument()
  })
})
