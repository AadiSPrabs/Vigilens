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
