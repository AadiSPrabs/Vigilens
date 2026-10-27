import React from 'react'

export default function Banner({ fromFixture }) {
  if (!fromFixture) return null
  return (
    <div className="banner" role="status" aria-live="polite">
      SAMPLE DATA - not a real audit
    </div>
  )
}
