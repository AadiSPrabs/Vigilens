export type ThemePref = "light" | "dark" | "system";
export const THEME_STORAGE_KEY = "vigilens-theme";

export function readThemePref(): ThemePref {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyThemePref(pref: ThemePref) {
  const dark =
    pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
}

export function writeThemePref(pref: ThemePref) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    /* storage unavailable; the choice still applies for this page view */
  }
}

export const THEME_INIT_SCRIPT = `(function(){try{var v=localStorage.getItem("${THEME_STORAGE_KEY}");var p=(v==="light"||v==="dark"||v==="system")?v:"system";var d=p==="dark"||(p==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;if(d)r.classList.add("dark");r.style.colorScheme=d?"dark":"light";}catch(e){}})();`;
