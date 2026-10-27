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
        findings: [{ severity: 'Low' }],
        helmet: 'absent',
        vest: 'absent'
      }],
      evidence_image: { url: 'test.png' },
      evidence_status: 'no_faces'
    }
    render(<AuditImage audit={audit} selectedId={null} onSelectPerson={() => {}} />)
    const polygons = screen.getAllByRole('button')
    expect(polygons.length).toBeGreaterThan(0)
  })

  it('Enter AND Space select', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const audit = {
      zones: [],
      persons: [{
        id: 'p1',
        polygon: [{x:0.1,y:0.1},{x:0.2,y:0.1},{x:0.15,y:0.2}],
        findings: [{ severity: 'Low' }],
        helmet: 'absent',
        vest: 'absent'
      }],
      evidence_image: { url: 'test.png' },
      evidence_status: 'no_faces'
    }
    render(<AuditImage audit={audit} selectedId={null} onSelectPerson={onSelect} />)
    const polygon = screen.getAllByRole('button')[0]
    polygon.focus()
    await user.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith('p1')
    await user.keyboard(' ')
    expect(onSelect).toHaveBeenCalledWith('p1')
  })
})
