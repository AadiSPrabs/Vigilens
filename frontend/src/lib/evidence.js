// Evidence format per CONTRACT v0.2
// Use ONLY audit.evidence_image.url. If missing or evidence_status is "masking_failed" 
// or image fails to load, show "Masked evidence unavailable" state and disable any evidence export.
// NEVER fall back to the original image as evidence.
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
