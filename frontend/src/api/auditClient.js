// Backend adapter - frontend never calls Meta APIs
const BACKEND_ENDPOINT = '/audit'
const DEFAULT_BASE = 'http://localhost:8000'

import { samples } from '../fixtures'
import { polygonArea, selfIntersects } from '../lib/geometry'
import { buildAuditRequest } from '../lib/requestBuilder'

// Lazy load fixtures
let fixturesCache = null
async function loadFixtures() {
  if (fixturesCache) return fixturesCache
  const [s1, s2, s3] = await Promise.all([
    import('../fixtures/sample1.json'),
    import('../fixtures/sample2.json'),
    import('../fixtures/sample3.json')
  ])
  fixturesCache = {
    'sample-1': s1.default || s1,
    'sample-2': s2.default || s2,
    'sample-3': s3.default || s3
  }
  return fixturesCache
}

function isValidNumber(n) {
  return typeof n === 'number' && !isNaN(n) && isFinite(n)
}

export function validateAudit(audit) {
  if (!audit || typeof audit !== 'object') {
    throw new Error('Invalid audit: must be an object')
  }
  const allowedSchemas = ['0.2', '0.2-local-draft']
  if (!allowedSchemas.includes(audit.schema_version)) {
    throw new Error('Invalid audit: unsupported schema_version')
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
  const allowedSeverity = ['Critical', 'Medium', 'Low']
  const allowedEvidenceStatus = ['unavailable', 'masked', 'no_faces', 'masking_failed']
  const allowedZoneMembership = ['known', 'unknown']
  
  if (audit.evidence_status && !allowedEvidenceStatus.includes(audit.evidence_status)) {
    throw new Error('Invalid audit: invalid evidence_status')
  }
  if (audit.zone_membership_status && !allowedZoneMembership.includes(audit.zone_membership_status)) {
    throw new Error('Invalid audit: invalid zone_membership_status')
  }
  
  const zoneIds = new Set()
  const personIds = new Set()
  const findingIds = new Set()
  
  for (const zone of audit.zones) {
    if (zoneIds.has(zone.id)) throw new Error('Invalid audit: duplicate zone id')
    zoneIds.add(zone.id)
    if (!Array.isArray(zone.points)) throw new Error('Invalid audit: zone points must be array')
    if (zone.points.length < 3) throw new Error('Invalid audit: polygon must have at least 3 points')
    if (polygonArea(zone.points) === 0) throw new Error('Invalid audit: zero-area polygon')
    if (selfIntersects(zone.points)) throw new Error('Invalid audit: self-intersecting polygon')
    for (const p of zone.points) {
      if (typeof p.x === 'boolean' || typeof p.y === 'boolean') throw new Error('Invalid audit: coordinates cannot be boolean')
      if (!isValidNumber(p.x) || !isValidNumber(p.y)) throw new Error('Invalid audit: point coordinates must be valid numbers')
      if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) throw new Error('Invalid audit: coordinates must be in range 0-1')
    }
  }
  
  for (const person of audit.persons) {
    if (personIds.has(person.id)) throw new Error('Invalid audit: duplicate person id')
    personIds.add(person.id)
    if (!Array.isArray(person.polygon)) throw new Error('Invalid audit: person polygon must be array')
    if (person.polygon.length < 3) throw new Error('Invalid audit: polygon must have at least 3 points')
    if (polygonArea(person.polygon) === 0) throw new Error('Invalid audit: zero-area polygon')
    if (selfIntersects(person.polygon)) throw new Error('Invalid audit: self-intersecting polygon')
    for (const p of person.polygon) {
      if (typeof p.x === 'boolean' || typeof p.y === 'boolean') throw new Error('Invalid audit: coordinates cannot be boolean')
      if (!isValidNumber(p.x) || !isValidNumber(p.y)) throw new Error('Invalid audit: point coordinates must be valid numbers')
      if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) throw new Error('Invalid audit: coordinates must be in range 0-1')
    }
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
  
  if (Array.isArray(audit.zone_ids)) {
    for (const zid of audit.zone_ids) {
      if (zid !== null && !zoneIds.has(zid)) throw new Error('Invalid audit: zone_ids entry not in zones')
    }
  }
  
  return true
}

export async function checkHealth(baseUrl) {
  try {
    const resp = await fetch((baseUrl || DEFAULT_BASE) + '/health')
    if (!resp.ok) return { ok: false }
    const data = await resp.json()
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: e }
  }
}

export async function analyzeImage({ file, zones, sampleId }, options = {}) {
  const { signal, snapshot, idempotencyKey } = options
  const mode = import.meta.env.VITE_AUDIT_MODE || 'fixture'
  
  if (mode === 'fixture') {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(resolve, 800)
      if (signal) {
        signal.addEventListener('abort', () => {
          clearTimeout(timeout)
          reject(new DOMException('Aborted', 'AbortError'))
        })
      }
    })
    
    if (!sampleId) {
      throw new Error('Fixture mode only has results for the bundled sample images. Pick a sample, or switch to backend mode.')
    }
    
    const fixtures = await loadFixtures()
    if (fixtures[sampleId]) {
      const audit = fixtures[sampleId]
      validateAudit(audit)
      return { audit, snapshot }
    }
    
    throw new Error('Fixture mode only has results for the bundled sample images. Pick a sample, or switch to backend mode.')
  }
  
  const baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE
  const { formData } = buildAuditRequest(file, zones)
  const key = idempotencyKey || crypto.randomUUID()
  
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort('timeout'), 60000)
  if (signal) {
    signal.addEventListener('abort', () => controller.abort(signal.reason))
  }
  
  try {
    const response = await fetch(baseUrl + BACKEND_ENDPOINT, {
      method: 'POST',
      body: formData,
      headers: { 'Idempotency-Key': key },
      signal: controller.signal
    })
    
    if (response.status === 503) {
      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('application/json')) {
        try {
          const errJson = await response.json()
          if (errJson.error && errJson.error.message) {
            throw new Error(errJson.error.message)
          }
        } catch (e) {
          if (e.message && e.message.includes('FIXTURE')) throw e
        }
      }
      // Could be FIXTURE_NOT_CONFIGURED or LOCAL_CACHE_FULL
      throw new Error('Service unavailable')
    }
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After')
      throw new Error(`Rate limited. Retry-After: ${retryAfter || 'unknown'}`)
    }
    if (response.status === 415) {
      throw new Error('Unsupported media type')
    }
    if (response.status === 409) {
      throw new Error('IDEMPOTENCY_CONFLICT')
    }
    if (response.status === 400) {
      throw new Error('INVALID_IDEMPOTENCY_KEY')
    }
    if (response.status === 413) {
      throw new Error('ZONES_TOO_LARGE')
    }
    if (response.status === 422) {
      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('application/json')) {
        try {
          const errJson = await response.json()
          if (errJson.error && errJson.error.message) {
            throw new Error(errJson.error.message)
          }
        } catch (e) {}
      }
      throw new Error('Unprocessable entity')
    }
    
    if (!response.ok) {
      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('application/json')) {
        try {
          const errJson = await response.json()
          if (errJson.error && errJson.error.message) {
            throw new Error(errJson.error.message)
          }
        } catch (e) {
          if (e.message && !e.message.includes('JSON')) throw e
        }
      }
      throw new Error(`Backend error: ${response.status}`)
    }
    
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      throw new Error('Invalid response format')
    }
    
    const audit = await response.json()
    validateAudit(audit)
    return { audit, snapshot, idempotencyKey: key }
  } catch (err) {
    if (err.name === 'AbortError' || err === 'timeout') {
      throw new Error('No response yet; the audit may still be running')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}
