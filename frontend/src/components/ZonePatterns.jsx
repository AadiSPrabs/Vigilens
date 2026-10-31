import React from 'react'

/**
 * Shared hatch patterns for the audit and editor overlays.
 *
 * `surface` namespaces the pattern ids so the evidence SVG and the editor SVG
 * can coexist without referencing each other's defs. Colours come from CSS
 * classes, never from JSX attributes.
 */
export default function ZonePatterns({ surface }) {
  return (
    <defs>
      <pattern
        id={`${surface}-hazard-pattern`}
        patternUnits="userSpaceOnUse"
        width="0.04"
        height="0.04"
        patternTransform="rotate(45)"
      >
        <rect className="zone-pattern__base zone-pattern__base--hazard" width="0.04" height="0.04" />
        <line className="zone-pattern__line zone-pattern__line--hazard" x1="0" y1="0" x2="0" y2="0.04" strokeWidth="0.002" />
        <line className="zone-pattern__line zone-pattern__line--ink" x1="0.02" y1="0" x2="0.02" y2="0.04" strokeWidth="0.002" />
      </pattern>
      <pattern
        id={`${surface}-restricted-pattern`}
        patternUnits="userSpaceOnUse"
        width="0.04"
        height="0.04"
        patternTransform="rotate(45)"
      >
        <rect className="zone-pattern__base" width="0.04" height="0.04" />
        <line className="zone-pattern__line zone-pattern__line--restricted" x1="0" y1="0" x2="0" y2="0.04" strokeWidth="0.002" />
        <line className="zone-pattern__line zone-pattern__line--ink" x1="0.02" y1="0" x2="0.02" y2="0.04" strokeWidth="0.002" />
      </pattern>
    </defs>
  )
}
