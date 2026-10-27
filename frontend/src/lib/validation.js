// Frontend pre-checks before upload
export function preCheckFile(file) {
  if (!file) return { ok: false, message: 'No file selected' }
  if (file.size > 15000000) {
    return { ok: false, message: 'File too large. Maximum size is 15 MB.' }
  }
  const validTypes = ['image/jpeg', 'image/png', 'image/webp']
  if (!validTypes.includes(file.type)) {
    return { ok: false, message: 'Invalid file type. Please upload jpg, png, or webp.' }
  }
  return { ok: true }
}

export function preCheckZones(zones) {
  if (!Array.isArray(zones)) return { ok: true }
  if (zones.length > 20) {
    return { ok: false, message: 'Too many zones. Maximum is 20.' }
  }
  for (const zone of zones) {
    if (Array.isArray(zone.points) && zone.points.length > 100) {
      return { ok: false, message: 'Too many points per polygon. Maximum is 100.' }
    }
  }
  return { ok: true }
}

export function preCheckImageDimensions(width, height) {
  if (width * height > 16000000) {
    return { ok: false, message: 'Image too large. Maximum is 16 megapixels.' }
  }
  if (width > 4096 || height > 4096) {
    return { ok: false, message: 'Image dimensions too large. Maximum is 4096x4096.' }
  }
  return { ok: true }
}
