import React, { useEffect, useState } from 'react'
import { MoonIcon, MonitorIcon, SunIcon } from './Icons'
import { applyTheme, readStoredTheme, storeTheme } from '../lib/theme'

const OPTIONS = [
  { value: 'light', label: 'Light', Icon: SunIcon },
  { value: 'dark', label: 'Dark', Icon: MoonIcon },
  { value: 'system', label: 'System', Icon: MonitorIcon }
]

export default function ThemeToggle() {
  const [mode, setMode] = useState(readStoredTheme)

  useEffect(() => {
    applyTheme(mode)
  }, [mode])

  const selectMode = (nextMode) => {
    setMode(nextMode)
    storeTheme(nextMode)
    applyTheme(nextMode)
  }

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Appearance">
      {OPTIONS.map(({ value, label, Icon }) => (
        <label
          key={value}
          className="theme-toggle__option"
          title={`${label} theme`}
        >
          <input
            type="radio"
            name="vigilens-theme-mode"
            value={value}
            checked={mode === value}
            onChange={() => selectMode(value)}
            aria-label={`${label} theme`}
          />
          <Icon size={16} className="theme-toggle__icon" />
          <span className="theme-toggle__label">{label}</span>
        </label>
      ))}
    </div>
  )
}
