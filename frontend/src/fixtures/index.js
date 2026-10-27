// Sample images and preset zones for Phase 1
// Figure positions are documented in normalized coordinates (0-1, origin top-left)
// for alignment with Phase 2 polygons

import sample1Img from './sample1.png'
import sample2Img from './sample2.png'
import sample3Img from './sample3.png'

// SAMPLE 1 - Compliant site
// Figures (normalized coords):
// - Person 1 (compliant): center roughly (0.3125, 0.819) - ellipse at cx=400,cy=520 in 1280x720
// - Person 2 (compliant): center roughly (0.625, 0.819) - ellipse at cx=800,cy=530
// Preset zone: covers general work area
export const sample1 = {
  id: 'sample-1',
  imageSrc: sample1Img,
  presetZones: [
    {
      id: 'zone-1',
      name: 'Work Area',
      hazard: false,
      points: [
        { x: 0.2, y: 0.7 },
        { x: 0.8, y: 0.7 },
        { x: 0.8, y: 0.95 },
        { x: 0.2, y: 0.95 }
      ]
    }
  ]
}

// SAMPLE 2 - Missing PPE
// Figures:
// - Person 1 (missing helmet): (0.1953, 0.7639) at cx=250,cy=540 - IN hazard zone
// - Person 2 (missing vest): (0.2734, 0.7639) at cx=350,cy=550 - IN hazard zone
export const sample2 = {
  id: 'sample-2',
  imageSrc: sample2Img,
  presetZones: [
    {
      id: 'zone-1',
      name: 'Crane Zone',
      hazard: true,
      points: [
        { x: 0.0625, y: 0.347 },
        { x: 0.375, y: 0.347 },
        { x: 0.375, y: 0.694 },
        { x: 0.0625, y: 0.694 }
      ]
    }
  ]
}

// SAMPLE 3 - Hazard intrusion with mixed cases
// Figures:
// - Person 4: (0.234375, 0.7778) at cx=300,cy=560 - IN hazard zone, findings [Low,Critical,Medium] with worst_severity Critical, NO helmet
// - Person 5: (0.3515625, 0.7917) at cx=450,cy=570 - IN hazard zone, mixed findings NO worst_severity
// - Person 6: (0.46875, 0.8056) at cx=600,cy=580 - IN hazard zone, has finding with severity "High"
export const sample3 = {
  id: 'sample-3',
  imageSrc: sample3Img,
  presetZones: [
    {
      id: 'zone-1',
      name: 'Crane Zone',
      hazard: true,
      points: [
        { x: 0.117, y: 0.278 },
        { x: 0.508, y: 0.278 },
        { x: 0.508, y: 0.722 },
        { x: 0.117, y: 0.722 }
      ]
    }
  ]
}

export const samples = [sample1, sample2, sample3]
