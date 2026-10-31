# Vigilens backend skeleton

Local-only skeleton for `POST /audit`, v0.2 shape, sample data only.

**Not a real audit yet.** It does not call SAM, Muse, or any paid API.
It validates the request (zones, file type, size, decoded dimensions),
then returns `sample-audit-v0.2.json` with the request's zones echoed,
a fresh `audit_id`, and the uploaded image's real dimensions.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

## Test

```bash
curl -F "image=@photo.jpg" \
  -F 'zones=[{"id":"zone-1","name":"Crane Zone","hazard":true,"points":[{"x":0.1,"y":0.2},{"x":0.6,"y":0.2},{"x":0.6,"y":0.8},{"x":0.1,"y":0.8}]}]' \
  http://localhost:8000/audit
```

Frontend: set `VITE_API_BASE_URL=http://localhost:8000` and
`VITE_AUDIT_MODE=backend` when you are ready to swap from fixtures.

## Agreed, and implemented here

- Endpoint `POST /audit`, multipart `image` + `zones` JSON string
- CORS: `http://localhost:5173` and `http://127.0.0.1:5173` only
- Caps: 15,000,000 bytes, 4096×4096, 16 MP, 20 zones, 100 points/polygon
- Errors as `{"error": {"code": "...", "message": "..."}}`: 400, 413, 415, 422
- v0.2 fields: `schema_version`, `ruleset_version`, `source`, `created_at`,
  finding `id`/`kind`/`zone_id`, `worst_severity` (string|null),
  `evidence_image.url`, `evidence_status`

## Not implemented yet — do not demo these as real

- SAM segmentation, Muse reasoning, deterministic severity in code
  (the sample's findings are fixture data, not model output)
- Face masking and serving a real masked image at `/evidence/<audit_id>.png`
  (the URL in the sample response is the agreed shape only)
- Real latency measurement vs the 60 s timeout
- Deployed base URL, auth/spending guard for a public demo

## Next steps, in order

1. Face-masking implementation choice (research before coding)
2. Wire SAM + Muse in place of the sample, keeping the same response shape
3. One real call, measure latency, report it to Raakin
4. Serve the real masked image at the evidence URL
