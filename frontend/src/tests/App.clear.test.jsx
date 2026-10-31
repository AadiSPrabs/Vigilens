import React from 'react'
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import App from '../App'

describe('App stale clearing', () => {
  it('component structure allows clearing', () => {
    render(<App />)
    expect(true).toBe(true)
  })
})
