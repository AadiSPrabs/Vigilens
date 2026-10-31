import type { Audit, Zone } from "../types";

const LOADED_AT = "2026-10-31T10:00:00Z";

export type SampleId = "sample-1" | "sample-2" | "sample-3";

export const SAMPLE_PRESET_ZONES: Record<SampleId, Zone[]> = {
  "sample-1": [
    {
      id: "zone-1",
      name: "Walkway",
      hazard: false,
      points: [
        { x: 0.08, y: 0.25 },
        { x: 0.92, y: 0.25 },
        { x: 0.92, y: 0.9 },
        { x: 0.08, y: 0.9 },
      ],
    },
  ],
  "sample-2": [
    {
      id: "zone-1",
      name: "Lift Zone",
      hazard: true,
      points: [
        { x: 0.1, y: 0.15 },
        { x: 0.55, y: 0.15 },
        { x: 0.55, y: 0.85 },
        { x: 0.1, y: 0.85 },
      ],
    },
    {
      id: "zone-2",
      name: "Stores",
      hazard: false,
      points: [
        { x: 0.6, y: 0.3 },
        { x: 0.92, y: 0.3 },
        { x: 0.92, y: 0.85 },
        { x: 0.6, y: 0.85 },
      ],
    },
  ],
  "sample-3": [
    {
      id: "zone-1",
      name: "Crane Zone",
      hazard: true,
      points: [
        { x: 0.1, y: 0.2 },
        { x: 0.6, y: 0.2 },
        { x: 0.6, y: 0.8 },
        { x: 0.1, y: 0.8 },
      ],
    },
    {
      id: "zone-2",
      name: "Storage Yard",
      hazard: false,
      points: [
        { x: 0.65, y: 0.2 },
        { x: 0.95, y: 0.2 },
        { x: 0.95, y: 0.8 },
        { x: 0.65, y: 0.8 },
      ],
    },
  ],
};

function box(x0: number, y0: number, x1: number, y1: number) {
  return [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
}

const AUDIT_1: Audit = {
  audit_id: "fixture-sample-1",
  schema_version: "0.2-local-draft",
  source: "fixture",
  fixture_loaded_at: LOADED_AT,
  fixture_notice: "SAMPLE DATA - not a real audit",
  created_at: null,
  image: { id: "img-sample-1", width: 1280, height: 720 },
  evidence_image: null,
  evidence_status: "unavailable",
  evidence_export_allowed: false,
  zones: SAMPLE_PRESET_ZONES["sample-1"],
  persons: [
    {
      id: "person-1",
      polygon: box(0.25, 0.35, 0.35, 0.75),
      helmet: "present",
      vest: "present",
      zone_id: "zone-1",
      zone_ids: ["zone-1"],
      zone_membership_status: "known",
      worst_severity: null,
      findings: [],
    },
    {
      id: "person-2",
      polygon: box(0.6, 0.35, 0.7, 0.75),
      helmet: "present",
      vest: "present",
      zone_id: "zone-1",
      zone_ids: ["zone-1"],
      zone_membership_status: "known",
      worst_severity: null,
      findings: [],
    },
  ],
};

const AUDIT_2: Audit = {
  audit_id: "fixture-sample-2",
  schema_version: "0.2-local-draft",
  source: "fixture",
  fixture_loaded_at: LOADED_AT,
  fixture_notice: "SAMPLE DATA - not a real audit",
  created_at: null,
  image: { id: "img-sample-2", width: 1280, height: 720 },
  evidence_image: null,
  evidence_status: "unavailable",
  evidence_export_allowed: false,
  zones: SAMPLE_PRESET_ZONES["sample-2"],
  persons: [
    {
      id: "person-1",
      polygon: box(0.3, 0.3, 0.42, 0.7),
      helmet: "absent",
      vest: "absent",
      zone_id: "zone-1",
      zone_ids: ["zone-1"],
      zone_membership_status: "known",
      worst_severity: "Critical",
      findings: [
        {
          id: "f-1",
          rule_id: "NO_HELMET_IN_HAZARD",
          kind: "violation",
          severity: "Critical",
          zone_id: "zone-1",
          message: "Helmet absent in Lift Zone.",
          review_state: "needs_human_review",
          recheck_trace: ["Illustrative step 1", "Illustrative step 2"],
        },
        {
          id: "f-2",
          rule_id: "NO_VEST_IN_HAZARD",
          kind: "violation",
          severity: "Critical",
          zone_id: "zone-1",
          message: "Hi-vis vest absent in Lift Zone.",
          review_state: "auto",
          recheck_trace: ["Illustrative step 1"],
        },
      ],
    },
    {
      id: "person-2",
      polygon: box(0.66, 0.32, 0.74, 0.72),
      helmet: "present",
      vest: "present",
      zone_id: "zone-2",
      zone_ids: ["zone-2"],
      zone_membership_status: "known",
      worst_severity: null,
      findings: [],
    },
  ],
};

const AUDIT_3: Audit = {
  audit_id: "fixture-sample-3",
  schema_version: "0.2-local-draft",
  source: "fixture",
  fixture_loaded_at: LOADED_AT,
  fixture_notice: "SAMPLE DATA - not a real audit",
  created_at: null,
  image: { id: "img-sample-3", width: 1280, height: 720 },
  evidence_image: null,
  evidence_status: "unavailable",
  evidence_export_allowed: false,
  zones: SAMPLE_PRESET_ZONES["sample-3"],
  persons: [
    {
      id: "person-1",
      polygon: box(0.3, 0.3, 0.45, 0.7),
      helmet: "absent",
      vest: "present",
      zone_id: "zone-1",
      zone_ids: ["zone-1"],
      zone_membership_status: "known",
      worst_severity: "Critical",
      findings: [
        {
          id: "f-5",
          rule_id: "EDGE_PROXIMITY",
          kind: "violation",
          severity: "Medium",
          zone_id: "zone-1",
          message: "Person within 0.05 of the crane zone edge.",
          review_state: "auto",
          recheck_trace: [],
        },
        {
          id: "f-1",
          rule_id: "NO_HELMET_IN_HAZARD",
          kind: "violation",
          severity: "Critical",
          zone_id: "zone-1",
          message: "Helmet absent in Crane Zone.",
          review_state: "needs_human_review",
          recheck_trace: ["Illustrative step 1", "Illustrative step 2"],
        },
      ],
    },
    {
      id: "person-2",
      polygon: box(0.7, 0.3, 0.82, 0.7),
      helmet: "present",
      vest: "present",
      zone_id: "zone-2",
      zone_ids: ["zone-2"],
      zone_membership_status: "known",
      worst_severity: "Medium",
      findings: [
        {
          id: "f-2",
          rule_id: "INTRUSION_RESTRICTED",
          kind: "violation",
          severity: "Medium",
          zone_id: "zone-2",
          message: "Person in a restricted-only zone.",
          review_state: "auto",
          recheck_trace: [],
        },
      ],
    },
    {
      id: "person-3",
      polygon: box(0.15, 0.35, 0.25, 0.65),
      helmet: "present",
      vest: "unknown",
      zone_id: "zone-1",
      zone_ids: ["zone-1"],
      zone_membership_status: "known",
      worst_severity: null,
      findings: [
        {
          id: "f-3",
          rule_id: "VEST_UNKNOWN",
          kind: "uncertainty",
          severity: null,
          zone_id: "zone-1",
          message: "Hi-vis vest could not be confirmed. Needs human review.",
          review_state: "needs_human_review",
          recheck_trace: ["Illustrative: vest region occluded"],
        },
      ],
    },
    {
      id: "person-4",
      polygon: box(0.03, 0.45, 0.08, 0.85),
      helmet: "absent",
      vest: "present",
      zone_id: null,
      zone_ids: [],
      zone_membership_status: "known",
      worst_severity: "Low",
      findings: [
        {
          id: "f-4",
          rule_id: "HELMET_ADVISORY",
          kind: "violation",
          severity: "Low",
          zone_id: null,
          message: "Helmet absent outside all zones. Advisory only.",
          review_state: "auto",
          recheck_trace: [],
        },
      ],
    },
  ],
};

export const FIXTURE_AUDITS: Record<SampleId, Audit> = {
  "sample-1": AUDIT_1,
  "sample-2": AUDIT_2,
  "sample-3": AUDIT_3,
};
