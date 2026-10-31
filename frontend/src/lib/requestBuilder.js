import { polygonArea, selfIntersects } from './geometry'

function stripZone(zone) {
  if (!zone || typeof zone !== 'object') return null
  const points = Array.isArray(zone.points) ? zone.points.map(p => ({ x: p.x, y: p.y })) : []
  return {
    id: zone.id,
    name: zone.name,
    hazard: zone.hazard,
    points
  }
}

export function buildAuditRequest(file, zones) {
  const strippedZones = (Array.isArray(zones) ? zones : []).map(stripZone).filter(Boolean)
  const formData = new FormData()
  if (file) formData.append('image', file)
  formData.append('zones', JSON.stringify(strippedZones))
  const idempotencyKey = crypto.randomUUID()
  return { formData, idempotencyKey, zones: strippedZones }
}
