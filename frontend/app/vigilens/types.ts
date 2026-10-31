export type Point = { x: number; y: number };

export type Zone = {
  id: string;
  name: string;
  hazard: boolean;
  points: Point[];
};

export type PpeState = "present" | "absent" | "unknown";

export type Finding = {
  id: string;
  rule_id: string;
  kind: string;
  severity: string | null;
  zone_id: string | null;
  message: string;
  review_state: string;
  recheck_trace: string[];
};

export type Person = {
  id: string;
  polygon: Point[];
  helmet: PpeState;
  vest: PpeState;
  zone_id: string | null;
  zone_ids: string[];
  zone_membership_status: string;
  worst_severity: string | null;
  findings: Finding[];
};

export type Audit = {
  audit_id: string;
  schema_version: string;
  source: "fixture" | "backend";
  fixture_loaded_at: string | null;
  fixture_notice: string | null;
  created_at: string | null;
  image: { id: string; width: number; height: number };
  evidence_image: { url: string; width: number; height: number } | null;
  evidence_status: string;
  evidence_export_allowed: boolean;
  zones: Zone[];
  persons: Person[];
};

export type ReviewDecision = "unreviewed" | "reviewed" | "needs_human_review";
