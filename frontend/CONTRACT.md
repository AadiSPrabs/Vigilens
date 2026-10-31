# Vigilens API Contract (v0.2-local-draft)

## Request
`POST /audit` (multipart/form-data)
*   **Headers:**
    *   `Idempotency-Key`: ASCII 1-128 chars. Generate via `crypto.randomUUID()` per image+zones snapshot. Reuse for "Try again".
    *   *Note:* Do not manually set `Content-Type` (allow browser to set boundary).
*   **Body:**
    *   `image`: File/Blob (jpeg/png/webp). Max 15MB, 4096x4096px, 16MP. Must be upright (no EXIF orientation, front-end bakes this).
    *   `zones`: JSON string. Max 20 zones, 3-100 points. Keys: `id` (string <=128), `name` (string <=200), `hazard` (bool), `points` (array of {x, y} finite numbers 0-1).

## Response
*   **Success (200 OK):**
    *   `audit_id` (string)
    *   `schema_version` (must be "0.2" or "0.2-local-draft")
    *   `ruleset_version` (string)
    *   `source` ("fixture" | "backend")
    *   `created_at` (UTC string or null)
    *   `image`: { `id`, `width`, `height` } (must exactly match uploaded decoded dimensions)
    *   `zones`: Echoed from request.
    *   `evidence_image`: { `url` } or null.
    *   `evidence_status`: "masked" | "no_faces" | "masking_failed" | "unavailable"
    *   `evidence_export_allowed`: bool
    *   `fixture_loaded_at`: UTC string (optional)
    *   `fixture_notice`: string (optional)
    *   `persons`: Array of detected people.
*   **Person Object:**
    *   `id`, `polygon`, `helmet`, `vest`
    *   `zone_id` (display zone, may be null), `zone_ids` (all containing zones)
    *   `zone_membership_status` ("known" | "unknown")
    *   `worst_severity` ("Critical" | "Medium" | "Low" | null)
    *   `findings`: Array of finding objects.
*   **Finding Object:**
    *   `id` (stable, required in backend mode)
    *   `rule_id`, `kind` ("violation" | "uncertainty")
    *   `severity` ("Critical" | "Medium" | "Low" | null)
    *   `zone_id` (the finding's zone)
    *   `message` (plain text)
    *   `review_state` ("auto" | "needs_human_review")

## Severity Matrix (Draft)
*   **Critical:** No PPE in `hazard:true` zone.
*   **Medium:** No PPE in `hazard:false` zone, OR intrusion in `hazard:false` zone.
*   **Low:** No PPE outside all drawn zones.

## Error Envelopes
Format: `{ "error": { "code": "...", "message": "..." } }`
Codes: `INVALID_REQUEST` (400), `INVALID_ZONES` (400), `IMAGE_TOO_LARGE` (413), `IMAGE_ORIENTATION_UNSUPPORTED` (422), `FIXTURE_NOT_CONFIGURED` (503).
