import sample1Audit from './sample1.json'
import sample2Audit from './sample2.json'
import sample3Audit from './sample3.json'
import sample1Img from './sample1.png'
import sample2Img from './sample2.png'
import sample3Img from './sample3.png'

// Zone coordinates are in normalized 0-1 space (exactly as specified)
// Image dimensions: 1280x720
// Person polygons are drawn in the SVG overlays (not baked into images)
// 
// Notes on sample positioning (for reference):
// - Person 1 (fully equipped): center roughly (0.3125, 0.819) - ellipse at cx=400,cy=520 in 1280x720
// - Person 2 (fully equipped): center roughly (0.625, 0.819) - ellipse at cx=800,cy=530

export const samples = [
  { id: 'sample-1', imageSrc: sample1Img, presetZones: sample1Audit.zones, name: 'Sample 1' },
  { id: 'sample-2', imageSrc: sample2Img, presetZones: sample2Audit.zones, name: 'Sample 2' },
  { id: 'sample-3', imageSrc: sample3Img, presetZones: sample3Audit.zones, name: 'Sample 3' }
]

export { sample1Audit, sample2Audit, sample3Audit }
