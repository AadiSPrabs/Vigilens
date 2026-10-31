import { describe, it, expect } from 'vitest'
import { polygonArea, selfIntersects } from '../../lib/geometry'

describe('polygon geometry', () => {
  it('polygonArea zero for degenerate', () => {
    expect(polygonArea([{x:0,y:0},{x:1,y:0},{x:0.5,y:0}])).toBe(0)
  })

  it('bowtie self-intersects', () => {
    const bowtie = [{x:0,y:0},{x:1,y:1},{x:1,y:0},{x:0,y:1}]
    expect(selfIntersects(bowtie)).toBe(true)
  })
})
