import React from 'react'

export default function Banner({ fromFixture, isStub, fixtureNotice }) {
  if (fixtureNotice) {
    return (
      <div className="banner banner-inline" role="status" aria-live="polite">
        {fixtureNotice}
      </div>
    )
  }
  if (isStub) {
    return (
      <div className="banner banner-inline banner-danger" role="status" aria-live="polite">
        Backend stub: sample output, not a real audit
      </div>
    )
  }
  if (!fromFixture) return null
  return (
    <div className="banner banner-inline banner-sample" role="status" aria-live="polite">
      SAMPLE DATA - not a real audit
    </div>
  )
}
