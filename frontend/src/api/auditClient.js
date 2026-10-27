// Backend adapter - frontend never calls Meta APIs
const BACKEND_ENDPOINT = '/audit' // POST {VITE_API_BASE_URL}/audit
const DEFAULT_BASE = 'http://localhost:8000'

import { samples } from '../fixtures'

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

export function validateAudit(audit) {
  if (!audit || typeof audit !== 'object') {
    throw new Error('Invalid audit: must be an object')
  }
  if (!audit.audit_id) throw new Error('Invalid audit: missing audit_id')
  if (!audit.image || typeof audit.image !== 'object') throw new Error('Invalid audit: missing image')
  if (typeof audit.image.width !== 'number' || typeof audit.image.height !== 'number') {
    throw new Error('Invalid audit: image must have width and height')
  }
  if (!Array.isArray(audit.zones)) throw new Error('Invalid audit: zones must be an array')
  if (!Array.isArray(audit.persons)) throw new Error('Invalid audit: persons must be an array')
  
  const allowedPPE = ['present', 'absent', 'unknown']
  
  for (const zone of audit.zones) {
    if (!Array.isArray(zone.points)) throw new Error('Invalid audit: zone points must be array')
    for (const p of zone.points) {
      if (typeof p.x !== 'number' || typeof p.y !== 'number') throw new Error('Invalid audit: point coordinates must be numbers')
      if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) throw new Error('Invalid audit: coordinates must be in range 0-1')
    }
  }
  
  for (const person of audit.persons) {
    if (!Array.isArray(person.polygon)) throw new Error('Invalid audit: person polygon must be array')
    for (const p of person.polygon) {
      if (typeof p.x !== 'number' || typeof p.y !== 'number') throw new Error('Invalid audit: point coordinates must be numbers')
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
  }
  
  return true
}

export async function analyzeImage({ file, zones, sampleId }, options = {}) {
  const { signal, snapshot } = options
  const mode = import.meta.env.VITE_AUDIT_MODE || 'fixture'
  
  if (mode === 'fixture') {
    // Simulate latency
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
  
  // Backend mode
  const baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE
  const formData = new FormData()
  if (file) formData.append('image', file)
  formData.append('zones', JSON.stringify(zones || []))
  
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort('timeout'), 60000)
  if (signal) {
    signal.addEventListener('abort', () => controller.abort(signal.reason))
  }
  
  try {
    const response = await fetch(baseUrl + BACKEND_ENDPOINT, {
      method: 'POST',
      body: formData,
      signal: controller.signal
    })
    
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After')
      throw new Error(`Rate limited. Retry-After: ${retryAfter || 'unknown'}`)
    }
    
    if (response.status === 415) {
      throw new Error('Unsupported media type')
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
    return { audit, snapshot }
  } catch (err) {
    if (err.name === 'AbortError' || err === 'timeout') {
      throw new Error('No response yet; the audit may still be running')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}
