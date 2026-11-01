import { IconDeviceDesktop, IconMoon, IconSun } from "@tabler/icons-react";

import type { ThemePref } from "../theme";

const OPTIONS: { value: ThemePref; label: string; Icon: typeof IconSun }[] = [
  { value: "light", label: "Light", Icon: IconSun },
  { value: "dark", label: "Dark", Icon: IconMoon },
  { value: "system", label: "System", Icon: IconDeviceDesktop },
];

export function ThemeToggle({ value, onChange }: { value: ThemePref; onChange: (v: ThemePref) => void }) {
  return (
    <div role="group" aria-label="Theme" className="inline-flex rounded-vg-md bg-vg-surface-sunken p-1">
      {OPTIONS.map(({ value: v, label, Icon }) => {
        const active = value === v;
        return (
          <button
            key={v}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(v)}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-vg-sm px-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring ${active ? "bg-vg-surface-raised font-medium text-vg-text shadow-vg-1" : "text-vg-text-secondary hover:text-vg-text"}`}
          >
            <Icon size={16} stroke={1.75} aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}
