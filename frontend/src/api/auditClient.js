// Backend adapter - frontend never calls Meta APIs
// unconfirmed - agree with backend teammate on endpoint path
const BACKEND_ENDPOINT = '/api/analyze' // unconfirmed - agree with backend teammate

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
  const { signal } = options
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
      return audit
    }
    
    throw new Error('Fixture mode only has results for the bundled sample images. Pick a sample, or switch to backend mode.')
  }
  
  // Backend mode
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const formData = new FormData()
  if (file) formData.append('image', file)
  formData.append('zones', JSON.stringify(zones || []))
  
  const response = await fetch(baseUrl + BACKEND_ENDPOINT, {
    method: 'POST',
    body: formData,
    signal
  })
  
  if (!response.ok) {
    throw new Error(`Backend error: ${response.status}`)
  }
  
  const audit = await response.json()
  validateAudit(audit)
  return audit
}
