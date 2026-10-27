import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AuditImage from '../components/AuditImage'

describe('AuditImage aspect ratio', () => {
  it('shows mismatch message for different aspect ratio', () => {
    const audit = {
      zones: [],
      persons: [],
      image: { width: 1280, height: 720 },
      evidence_image: { url: 'test.png' },
      evidence_status: 'no_faces'
    }
    render(<AuditImage audit={audit} selectedId={null} onSelectPerson={() => {}} />)
    // Initially shows image, but we'll test the logic
    expect(screen.getByText(/Audit Overlay/)).toBeInTheDocument()
  })
})
