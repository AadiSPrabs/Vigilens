const STORAGE_KEY = 'vigilens-theme'
const MODES = ['light', 'dark', 'system']

export const THEME_STORAGE_KEY = STORAGE_KEY
export const THEME_MODES = MODES

export function readStoredTheme() {
  if (typeof window === 'undefined') return 'system'
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return MODES.includes(value) ? value : 'system'
  } catch (e) {
    return 'system'
  }
}

export function storeTheme(mode) {
  if (!MODES.includes(mode)) return
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, mode)
  } catch (e) {
  }
}

export function applyTheme(mode) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (mode === 'light' || mode === 'dark') {
    root.setAttribute('data-theme', mode)
  } else {
    root.removeAttribute('data-theme')
  }
}
