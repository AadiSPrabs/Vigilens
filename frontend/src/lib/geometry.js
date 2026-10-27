// Pure geometry helpers for Vigilens
// Coordinates are normalised 0-1, origin top-left

export function clientToNormalised(e, imgElement) {
  const rect = imgElement.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width
  const y = (e.clientY - rect.top) / rect.height
  if (x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x, y }
}

export function toPoints(points) {
  return points.map(p => ({ x: p.x, y: p.y }))
}

export const zonesEqual = (a, b) => {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  return a.every((z, i) => {
    const bz = b[i]
    if (!bz) return false
    if (z.id !== bz.id) return false
    if (z.hazard !== bz.hazard) return false
    if (!Array.isArray(z.points) || !Array.isArray(bz.points)) return false
    if (z.points.length !== bz.points.length) return false
    return z.points.every((p, j) => {
      const bp = bz.points[j]
      return Math.abs(p.x - bp.x) < 1e-9 && Math.abs(p.y - bp.y) < 1e-9
    })
  })
}

export function polygonArea(points) {
  if (!Array.isArray(points) || points.length < 3) return 0
  let area = 0
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length
    area += points[i].x * points[j].y
    area -= points[j].x * points[i].y
  }
  return Math.abs(area) / 2
}

function segmentsIntersect(p1, p2, p3, p4) {
  const ccw = (a, b, c) => {
    const val = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)
    if (Math.abs(val) < 1e-10) return 0
    return val > 0 ? 1 : 2
  }
  const o1 = ccw(p1, p2, p3)
  const o2 = ccw(p1, p2, p4)
  const o3 = ccw(p3, p4, p1)
  const o4 = ccw(p3, p4, p2)
  if (o1 !== o2 && o3 !== o4) return true
  return false
}

export function selfIntersects(points) {
  if (!Array.isArray(points) || points.length < 4) return false
  for (let i = 0; i < points.length; i++) {
    const p1 = points[i]
    const p2 = points[(i + 1) % points.length]
    for (let j = i + 1; j < points.length; j++) {
      const p3 = points[j]
      const p4 = points[(j + 1) % points.length]
      if (Math.abs(i - j) === 1 || Math.abs(i - j) === points.length - 1) continue
      if (segmentsIntersect(p1, p2, p3, p4)) return true
    }
  }
  return false
}
