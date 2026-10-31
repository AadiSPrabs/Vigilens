import { zonesEqual } from './geometry'

// Pure function for determining if analysis can proceed
export function canAnalyse({ image, zones, runWithoutZones, sample }) {
  if (!image) return false
  if (runWithoutZones) {
    // For samples, fixture results only for preset zones
    if (sample && Array.isArray(sample.presetZones)) {
      // If zones differ from preset zones, cannot analyse with fixture results
      if (!zonesEqual(zones || [], sample.presetZones)) {
        return false
      }
    }
    return true
  }
  if (!Array.isArray(zones) || zones.length === 0) return false
  // For samples in fixture mode, must match preset zones
  if (sample && Array.isArray(sample.presetZones)) {
    if (!zonesEqual(zones, sample.presetZones)) {
      return false
    }
  }
  return true
}
