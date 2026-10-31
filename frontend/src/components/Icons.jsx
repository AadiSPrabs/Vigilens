import React from 'react'

function Icon({ children, size = 16, className = '', viewBox = '0 0 20 20' }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

export function SunIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <circle cx="10" cy="10" r="3.25" />
      <path d="M10 2.25v1.5M10 16.25v1.5M2.25 10h1.5M16.25 10h1.5M4.52 4.52l1.06 1.06M14.42 14.42l1.06 1.06M15.48 4.52l-1.06 1.06M5.58 14.42l-1.06 1.06" />
    </Icon>
  )
}

export function MoonIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="M16.25 12.2A6.6 6.6 0 0 1 7.8 3.75a6.75 6.75 0 1 0 8.45 8.45Z" />
    </Icon>
  )
}

export function MonitorIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <rect x="2.75" y="3.25" width="14.5" height="10.5" rx="1.5" />
      <path d="M7.25 16.75h5.5M10 13.75v3" />
    </Icon>
  )
}

export function InfoIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <circle cx="10" cy="10" r="7.25" />
      <path d="M10 9.25v4.25M10 6.5v.25" />
    </Icon>
  )
}

export function AlertIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="M10 3.1 17.15 16.4H2.85L10 3.1Z" />
      <path d="M10 7.5v3.75M10 14.1v.15" />
    </Icon>
  )
}

export function ChevronDownIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="m5.5 8 4.5 4.5L14.5 8" />
    </Icon>
  )
}

export function TrashIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="M3.75 5.75h12.5M8 3.5h4M5.5 5.75l.6 10.25h7.8l.6-10.25M8.25 9v4.5M11.75 9v4.5" />
    </Icon>
  )
}

export function CheckIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="m4.5 10.5 3.25 3.25 7.75-8" />
    </Icon>
  )
}

export function MinusIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="M4.5 10h11" />
    </Icon>
  )
}

export function CloseIcon({ size = 16, className }) {
  return (
    <Icon size={size} className={className}>
      <path d="m5 5 10 10M15 5 5 15" />
    </Icon>
  )
}

export function CameraFrameIcon({ size = 96, className }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M16 32V20a4 4 0 0 1 4-4h12M64 16h12a4 4 0 0 1 4 4v12M80 64v12a4 4 0 0 1-4 4H64M32 80H20a4 4 0 0 1-4-4V64" />
      <rect x="28" y="32" width="40" height="32" rx="6" />
      <circle cx="48" cy="48" r="8" />
      <path d="M40 32l3-5h10l3 5" />
    </svg>
  )
}

export function SeverityShape({ variant = 'unknown', size = 12 }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 12 12',
    'aria-hidden': true,
    focusable: 'false'
  }

  if (variant === 'critical') {
    return (
      <svg {...common}>
        <circle cx="6" cy="6" r="4.5" fill="currentColor" />
      </svg>
    )
  }

  if (variant === 'medium') {
    return (
      <svg {...common}>
        <path d="M6 1.6 11 10.4H1L6 1.6Z" fill="currentColor" />
      </svg>
    )
  }

  if (variant === 'low') {
    return (
      <svg {...common}>
        <rect x="1.75" y="1.75" width="8.5" height="8.5" rx="1" fill="currentColor" />
      </svg>
    )
  }

  if (variant === 'uncertain') {
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.25 2">
        <circle cx="6" cy="6" r="4.25" />
      </svg>
    )
  }

  if (variant === 'no-listed') {
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="m2.25 6.2 2.2 2.2 5.3-5.4" />
      </svg>
    )
  }

  return (
    <svg {...common} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M2.25 6h7.5" />
    </svg>
  )
}
