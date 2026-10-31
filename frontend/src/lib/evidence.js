// Evidence format per CONTRACT v0.2
// Use ONLY audit.evidence_image.url
export function resolveEvidence(audit) {
  const ev = audit?.evidence_image
  if (!ev || typeof ev !== 'object') {
    return { ok: false, src: null, status: 'missing', reason: 'Masked evidence unavailable' }
  }
  if (audit.evidence_status === 'masking_failed') {
    return { ok: false, src: null, status: 'masking_failed', reason: 'Masked evidence unavailable' }
  }
  if (typeof ev.url === 'string' && ev.url) {
    return { ok: true, src: ev.url, status: audit.evidence_status || 'ok', reason: null }
  }
  return { ok: false, src: null, status: 'missing', reason: 'Masked evidence unavailable' }
}

export async function verifyEvidenceExport(audit) {
  if (audit?.evidence_export_allowed !== true) return false
  const evidence = resolveEvidence(audit)
  if (!evidence.ok) return false
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      if (audit.image && img.naturalWidth === audit.image.width && img.naturalHeight === audit.image.height) {
        resolve(true)
      } else {
        resolve(false)
      }
    }
    img.onerror = () => resolve(false)
    img.src = evidence.src
  })
}
