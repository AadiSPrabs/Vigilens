import { IconPrinter } from "@tabler/icons-react";

import { ThemeToggle } from "./ThemeToggle";
import type { ThemePref } from "../theme";

type Props = {
  theme: ThemePref;
  onTheme: (v: ThemePref) => void;
  onExport: () => void;
  exportDisabled: boolean;
};

export function TopBar({ theme, onTheme, onExport, exportDisabled }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-vg-border bg-vg-surface/85 backdrop-blur-md supports-[not(backdrop-filter)]:bg-vg-surface">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-lg font-semibold tracking-tight text-vg-text">Vigilens</span>
          <span className="rounded-vg-sm border border-vg-border-strong px-2 py-0.5 text-xs font-medium text-vg-text-secondary">
            Fixture mode
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ThemeToggle value={theme} onChange={onTheme} />
          <button
            type="button"
            onClick={onExport}
            disabled={exportDisabled}
            aria-label="Export PDF"
            className="inline-flex min-h-10 items-center gap-2 rounded-vg-md border border-vg-border-strong px-3 text-sm font-medium text-vg-text hover:bg-vg-hover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
          >
            <IconPrinter size={16} stroke={1.75} aria-hidden="true" />
            <span>Export PDF</span>
          </button>
        </div>
      </div>
    </header>
  );
}
