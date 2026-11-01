import type { Finding, Person } from "./types";

export type SeverityKind = "critical" | "medium" | "low" | "uncertain" | "neutral" | "clear";

export function severityKind(severity: string | null | undefined, kind?: string): SeverityKind {
  if (kind === "uncertainty") return "uncertain";
  if (severity === "Critical") return "critical";
  if (severity === "Medium") return "medium";
  if (severity === "Low") return "low";
  return "neutral";
}

export const SEVERITY_LABEL: Record<SeverityKind, string> = {
  critical: "Critical",
  medium: "Medium",
  low: "Low",
  uncertain: "Uncertain - needs human check",
  neutral: "Neutral",
  clear: "No listed violations",
};

export const SEVERITY_RANK: Record<SeverityKind, number> = {
  critical: 0,
  medium: 1,
  low: 2,
  neutral: 3,
  clear: 4,
  uncertain: 5,
};

export function findingRank(f: Finding): number {
  if (f.kind === "uncertainty" || f.severity === null) return SEVERITY_RANK.uncertain;
  return SEVERITY_RANK[severityKind(f.severity)];
}

export function personOutline(person: Person): SeverityKind {
  if (person.worst_severity) return severityKind(person.worst_severity);
  if (
    person.findings.length === 0 &&
    person.helmet === "present" &&
    person.vest === "present"
  ) {
    return "clear";
  }
  return "neutral";
}
