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
  image: { id: string; width: number; height: number; pixel_digest?: string };
  evidence_image: { url: string; width: number; height: number } | null;
  evidence_status: string;
  evidence_export_allowed: boolean;
  zones: Zone[];
  persons: Person[];
  // Governed-backend honesty fields (absent on fixtures): origin of the readings
  // derived from the stored result's recorded response ids - never from server mode.
  readings_origin?: "synthetic" | "live_provider" | "unknown";
  readings_status?: string;
  zones_applied?: boolean;
  rechecks?: RecheckSurface;
};

// Deliberate rechecks are separate candidate observations bound to the exact immutable
// original. They never replace the original readings, are never auto-adopted, and are
// user-triggered per attempt only. Absent executor/grant config, the surface reports
// not_configured and unknown readings simply stay with human review.
export type RecheckSurface = {
  status: "not_configured" | "separate_candidates_require_review";
  attempts: RecheckAttempt[];
  original_result_unchanged: boolean;
  automatic_candidate_adoption?: boolean;
};

export type RecheckAttempt = {
  attempt_id: string;
  state: string;
  result: {
    helmet?: string;
    vest?: string;
    crop_person_association?: { basis?: string };
  } | null;
  retry_allowed: boolean;
  provider_calls_this_request: number | null;
  evidence_export_allowed: boolean;
  binding: { source_digest: string; result_sha256: string; person_id: string; attempt: number; crop_png_sha256: string };
  original_result_unchanged: boolean;
  candidate_adoption: string;
};

export type ReviewDecision = "unreviewed" | "reviewed" | "needs_human_review";

export type ClipFrameResult = {
  sample_index: number;
  requested_offset_seconds: number;
  timestamp_basis: string;
  source_clip_sha256: string;
  pixel_digest: string;
  width: number;
  height: number;
  image_job: { state: string; result: unknown; provider_calls_this_request?: number | null };
  provider_calls_this_sample: number | null;
  repeated_pixels_share_image_job: boolean;
};

export type ClipSummary = {
  source_clip_sha256: string;
  duration_seconds: number;
  requested_sample_count: number;
  completed_sample_count: number;
  frames: ClipFrameResult[];
  provider_calls_this_request: number | null;
  status: string; // "completed" | "partial_requires_operator_reconciliation" | ...
  frames_with_unassessed_people: number[];
  frames_with_unresolved_people: number[];
  attempted_is_not_resolved_assessment: boolean;
  completed_state_is_execution_terminal_not_assessment_complete: boolean;
  cross_frame_person_identity: string;
  sampled_frames_are_not_complete_clip_coverage: boolean;
  clip_intrusion_or_crossing: string;
  privacy_review_status: string;
  evidence_export_allowed: boolean;
  automatic_retry_allowed: boolean;
  report_integration: string;
  decoder_scope: string;
  private_clip_review_id?: string;
};

// Private-display ceremony: the treated preview session the backend binds to the
// exact source/result and the visitor account. The acknowledgment must name the
// exact derivative; the backend refuses anything else. Display-only: the treated
// image is shown in place and never exported.
// Optional offline face-check proposals (YuNet review aid). The backend applies
// NO automatic treatment, makes no provider calls, and labels the result
// fail-closed: proposals always need operator review, zero detections never
// means safe, and coverage stays unverified. Boxes are pixel corners
// [x1, y1, x2, y2]; review_region includes the proposal margin.
export type FaceProposal = {
  box: [number, number, number, number];
  review_region: [number, number, number, number];
  confidence: number;
  pass_scale: number;
  helmet_overlap_unchecked: boolean;
};

export type FaceProposalsResult = {
  source_pixel_digest: string;
  frame: [number, number];
  detector: string;
  threshold: number;
  proposals: FaceProposal[];
  status: string;
  coverage: string;
  zero_detections_means_safe: boolean;
  privacy_review_status: string;
  reason?: string;
  margin_policy?: string;
  mandatory_next_step?: string;
  automatic_treatment_applied: boolean;
  provider_calls_this_request: number;
};

export type PrivateDisplaySession = {
  session_id: string;
  source_digest: string;
  output_sha256: string;
  regions_digest: string;
  width: number;
  height: number;
  preview_url: string;
  warning?: string;
  notice?: string;
  expires_in_seconds?: number;
  evidence_export_allowed?: boolean;
};
