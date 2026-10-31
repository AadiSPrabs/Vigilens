import React from 'react'
import { AlertIcon, InfoIcon } from './Icons'

export default function Banner({ fromFixture, isStub, fixtureNotice }) {
  if (fixtureNotice) {
    return (
      <div className="notice notice--sample" role="status" aria-live="polite">
        <InfoIcon size={16} className="notice__icon" />
        <span className="notice__text">{fixtureNotice}</span>
      </div>
    )
  }
  if (isStub) {
    return (
      <div className="notice notice--danger" role="status" aria-live="polite">
        <AlertIcon size={16} className="notice__icon" />
        <span className="notice__text">Backend stub: sample output, not a real audit</span>
      </div>
    )
  }
  if (!fromFixture) return null
  return (
    <div className="notice notice--sample" role="status" aria-live="polite">
      <InfoIcon size={16} className="notice__icon" />
      <span className="notice__text">SAMPLE DATA - not a real audit</span>
    </div>
  )
}
