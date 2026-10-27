// Evidence format is NOT agreed with the backend (see CONTRACT.md section 4.4).
// Only this function reads audit.evidence_image
export function resolveEvidence(audit, originalSrc) {
  const ev = audit?.evidence_image
  if (ev && typeof ev === 'object') {
    if (typeof ev.url === 'string' && ev.url) {
      return { src: ev.url, backendMasked: true, note: null }
    }
    if (typeof ev.base64 === 'string' && ev.base64) {
      const mime = ev.mime || 'image/png'
      return { src: `data:${mime};base64,${ev.base64}`, backendMasked: true, note: null }
    }
  }
  return {
    src: originalSrc,
    backendMasked: false,
    note: 'Face masking is performed by the backend; not applied in sample mode.'
  }
}
