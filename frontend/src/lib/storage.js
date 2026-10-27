// Zone storage keyed by image name+size, in try/catch, tolerating empty/corrupt storage
// Only user-uploaded images use localStorage - samples NEVER read localStorage

const KEY_PREFIX = 'vigilens:zones:'

function makeKey(file) {
  if (!file) return null
  const name = file.name || 'unknown'
  const size = file.size || 0
  return KEY_PREFIX + name + ':' + size
}

export function saveZones(file, zones) {
  try {
    const key = makeKey(file)
    if (!key) return
    localStorage.setItem(key, JSON.stringify(zones))
  } catch (e) {
    // tolerate
  }
}

export function loadZones(file) {
  try {
    const key = makeKey(file)
    if (!key) return null
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed
  } catch (e) {
    return null
  }
}
