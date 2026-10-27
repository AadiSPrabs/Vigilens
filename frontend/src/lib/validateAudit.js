// Validate audit response per contract
export function validateAudit(audit, options = {}) {
  const { mode = 'fixture' } = options
  if (!audit || typeof audit !== 'object') {
    throw new Error('Invalid audit: must be an object')
  }
  const allowedSchemas = ['0.2', '0.2-local-draft']
  if (!allowedSchemas.includes(audit.schema_version)) {
    throw new Error(`Unsupported schema version: "${audit?.schema_version ?? 'missing'}" (expected "0.2" or "0.2-local-draft")`)
  }
  if (!audit.audit_id) throw new Error('Invalid audit: missing audit_id')
  if (!audit.image || typeof audit.image !== 'object') throw new Error('Invalid audit: missing image')
  if (typeof audit.image.width !== 'number' || typeof audit.image.height !== 'number') {
    throw new Error('Invalid audit: image must have width and height')
  }
  if (!Array.isArray(audit.zones)) throw new Error('Invalid audit: zones must be an array')
  if (!Array.isArray(audit.persons)) throw new Error('Invalid audit: persons must be an array')
  
  const allowedPPE = ['present', 'absent', 'unknown']
  const allowedKinds = ['violation', 'uncertainty']
  const allowedEvidenceStatus = ['unavailable', 'masked', 'no_faces', 'masking_failed']
  const allowedZoneMembership = ['known', 'unknown']
  
  if (audit.evidence_status && !allowedEvidenceStatus.includes(audit.evidence_status)) {
    throw new Error('Invalid audit: invalid evidence_status')
  }
  if (audit.zone_membership_status && !allowedZoneMembership.includes(audit.zone_membership_status)) {
    throw new Error('Invalid audit: invalid zone_membership_status')
  }
  
  const { polygonArea, selfIntersects } = require ? { polygonArea: () => 0, selfIntersects: () => false } : {}
  
  const zoneIds = new Set()
  const personIds = new Set()
  const findingIds = new Set()
  
  for (const zone of audit.zones) {
    if (zoneIds.has(zone.id)) throw new Error('Invalid audit: duplicate zone id')
    zoneIds.add(zone.id)
    if (!Array.isArray(zone.points)) throw new Error('Invalid audit: zone points must be array')
    if (zone.points.length < 3) throw new Error('Invalid audit: polygon must have at least 3 points')
  }
  
  for (const person of audit.persons) {
    if (personIds.has(person.id)) throw new Error('Invalid audit: duplicate person id')
    personIds.add(person.id)
    if (!Array.isArray(person.polygon)) throw new Error('Invalid audit: person polygon must be array')
    if (person.polygon.length < 3) throw new Error('Invalid audit: polygon must have at least 3 points')
    if (person.helmet && !allowedPPE.includes(person.helmet)) {
      throw new Error('Invalid audit: helmet must be present, absent, or unknown')
    }
    if (person.vest && !allowedPPE.includes(person.vest)) {
      throw new Error('Invalid audit: vest must be present, absent, or unknown')
    }
    if (person.findings && !Array.isArray(person.findings)) {
      throw new Error('Invalid audit: findings must be an array')
    }
    if (Array.isArray(person.findings)) {
      for (const finding of person.findings) {
        if (mode === 'backend') {
          if (!finding.id || typeof finding.id !== 'string' || finding.id === '') {
            throw new Error('Invalid audit: missing finding id in backend mode')
          }
        }
        if (finding.id) {
          if (findingIds.has(finding.id)) throw new Error('Invalid audit: duplicate finding id')
          findingIds.add(finding.id)
        }
        if (finding.kind && !allowedKinds.includes(finding.kind)) {
          throw new Error('Invalid audit: invalid finding kind')
        }
        if (finding.zone_id !== null && finding.zone_id !== undefined) {
          if (!zoneIds.has(finding.zone_id)) throw new Error('Invalid audit: finding.zone_id not in zones')
        }
      }
    }
  }
  
  return true
}
