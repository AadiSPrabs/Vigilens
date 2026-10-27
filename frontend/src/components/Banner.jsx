import React from 'react'

export default function Banner({ fromFixture, isStub, fixtureNotice }) {
  if (fixtureNotice) {
    return (
      <div className="banner" role="status" aria-live="polite">
        {fixtureNotice}
      </div>
    )
  }
  if (isStub) {
    return (
      <div className="banner" role="status" aria-live="polite" style={{ background: '#f87171', color: '#7f1d1d' }}>
        Backend stub: sample output, not a real audit
      </div>
    )
  }
  if (!fromFixture) return null
  return (
    <div className="banner" role="status" aria-live="polite">
      SAMPLE DATA - not a real audit
    </div>
  )
}
