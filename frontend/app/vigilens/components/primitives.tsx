import {
  IconCircle,
  IconCircleCheck,
  IconDiamond,
  IconLoader2,
  IconOctagon,
  IconQuestionMark,
  IconSquare,
  IconTriangle,
  IconX,
  IconCheck,
} from "@tabler/icons-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { severityKind, SEVERITY_LABEL, type SeverityKind } from "../severity";
import type { PpeState } from "../types";

const SEV_CLASS: Record<SeverityKind, string> = {
  critical: "bg-sev-critical-bg text-sev-critical-fg border-sev-critical-border",
  medium: "bg-sev-medium-bg text-sev-medium-fg border-sev-medium-border",
  low: "bg-sev-low-bg text-sev-low-fg border-sev-low-border",
  uncertain: "bg-sev-uncertain-bg text-sev-uncertain-fg border-sev-uncertain-border",
  neutral: "bg-sev-neutral-bg text-sev-neutral-fg border-sev-neutral-border",
  clear: "bg-sev-clear-bg text-sev-clear-fg border-sev-clear-border",
};

const SEV_ICON: Record<SeverityKind, typeof IconOctagon> = {
  critical: IconOctagon,
  medium: IconTriangle,
  low: IconCircle,
  uncertain: IconDiamond,
  neutral: IconSquare,
  clear: IconCircleCheck,
};

export function SeverityBadge({ severity, kind }: { severity: string | null; kind?: string }) {
  const k = severityKind(severity, kind);
  const Icon = SEV_ICON[k];
  let text: string;
  if (k === "uncertain") text = SEVERITY_LABEL.uncertain;
  else if (severity === null) text = "No severity";
  else text = severity;
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1.5 rounded-vg-sm border px-2 py-0.5 text-xs font-medium ${SEV_CLASS[k]}`}
    >
      <Icon size={14} stroke={2} aria-hidden="true" className="shrink-0" />
      <span className="break-words">{text}</span>
    </span>
  );
}

export function ClearBadge() {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-vg-sm border px-2 py-0.5 text-xs font-medium ${SEV_CLASS.clear}`} title="Not a safety clearance">
      <IconCircleCheck size={14} stroke={2} aria-hidden="true" />
      No listed violations
    </span>
  );
}

export function PpeChip({ label, state }: { label: string; state: PpeState }) {
  if (state === "present") {
    return (
      <span className="inline-flex items-center gap-1 rounded-vg-sm border border-vg-border px-2 py-0.5 text-xs text-vg-text">
        <IconCheck size={13} stroke={2.2} aria-hidden="true" />
        {label} present
      </span>
    );
  }
  if (state === "absent") {
    return (
      <span className={`inline-flex items-center gap-1 rounded-vg-sm border px-2 py-0.5 text-xs font-medium ${SEV_CLASS.critical}`}>
        <IconX size={13} stroke={2.2} aria-hidden="true" />
        {label} absent
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-vg-sm border px-2 py-0.5 text-xs font-medium ${SEV_CLASS.uncertain}`}>
      <IconQuestionMark size={13} stroke={2.2} aria-hidden="true" />
      {label}: Unclear - needs human check
    </span>
  );
}

export function EmptyState({ title, children, art }: { title?: string; children: ReactNode; art?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      {art}
      {title ? <h2 className="text-lg font-semibold text-vg-text">{title}</h2> : null}
      <p className="max-w-sm text-sm text-vg-text-secondary">{children}</p>
    </div>
  );
}

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-vg-md border border-sev-critical-border bg-sev-critical-bg p-4">
      <h2 className="text-base font-semibold text-sev-critical-fg">Analysis did not finish</h2>
      <p className="text-sm text-sev-critical-fg">{message}</p>
      <div>
        <Button type="button" variant="outline" className="min-h-10" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-vg-text-secondary">
      <IconLoader2 size={18} className="vg-motion animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
}
