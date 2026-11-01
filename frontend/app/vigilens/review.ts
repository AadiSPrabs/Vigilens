import type { Finding, ReviewDecision } from "./types";
import { severityKind } from "./severity";

export function decisionFor(finding: Finding, reviews: Record<string, ReviewDecision>): ReviewDecision {
  return reviews[finding.id] ?? (finding.review_state === "needs_human_review" ? "needs_human_review" : "unreviewed");
}

export const REVIEW_LABEL: Record<ReviewDecision, string> = {
  unreviewed: "Unreviewed",
  reviewed: "Reviewed",
  needs_human_review: "Needs human review",
};

export const SEVERITY_FILTERS = [
  { value: "all", label: "All severities" },
  { value: "Critical", label: "Critical" },
  { value: "Medium", label: "Medium" },
  { value: "Low", label: "Low" },
  { value: "uncertain", label: "Uncertain" },
  { value: "other", label: "Other" },
];

export function matchesSeverity(finding: Finding, filter: string) {
  if (filter === "all") return true;
  if (filter === "uncertain") return severityKind(finding.severity, finding.kind) === "uncertain";
  if (filter === "other") {
    const k = severityKind(finding.severity, finding.kind);
    return k === "neutral" && finding.kind !== "uncertainty";
  }
  return finding.severity === filter && finding.kind !== "uncertainty";
}

export function matchesZone(zoneId: string | null, filter: string) {
  if (filter === "all") return true;
  if (filter === "none") return zoneId === null;
  return zoneId === filter;
}
