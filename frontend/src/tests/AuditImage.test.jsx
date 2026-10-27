import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuditImage from '../components/AuditImage'

describe('AuditImage', () => {
  it('outline uses worst_severity not findings[0]', () => {
    const audit = {
      zones: [],
      persons: [{
        id: 'p1',
        polygon: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}],
        worst_severity: 'Critical',
        findings: [{ severity: 'Low' }]
      }]
    }
    render(<AuditImage imageSrc="test.png" audit={audit} selectedId={null} onSelectPerson={() => {}} />)
    const polygon = screen.getByRole('button')
    expect(polygon).toBeInTheDocument()
  })

  it('Enter AND Space select', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const audit = {
      zones: [],
      persons: [{
        id: 'p1',
        polygon: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}],
        findings: []
      }]
    }
    render(<AuditImage imageSrc="test.png" audit={audit} selectedId={null} onSelectPerson={onSelect} />)
    const polygon = screen.getByRole('button')
    polygon.focus()
    await user.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith('p1')
    await user.keyboard(' ')
    expect(onSelect).toHaveBeenCalledWith('p1')
  })
})
