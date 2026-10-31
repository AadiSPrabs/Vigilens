"""
Vigilens backend skeleton — /audit, v0.2 shape, FAKE data only.

This skeleton does NOT call SAM, Muse, or any paid API yet.
It validates the request exactly as agreed in CONTRACT v0.1 / v0.2, then
returns the labelled sample audit in sample-audit-v0.2.json, with the
zones echoed from the request and a fresh audit_id / created_at.

Run:
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000

Test:
  curl -F "image=@/path/to/photo.jpg" \
       -F 'zones=[{"id":"zone-1","name":"Crane Zone","hazard":true,"points":[{"x":0.1,"y":0.2},{"x":0.6,"y":0.2},{"x":0.6,"y":0.8},{"x":0.1,"y":0.8}]}]' \
       http://localhost:8000/audit

Agreed caps: 15,000,000 bytes, 4096x4096, 16 MP decoded, 20 zones, 100 points/polygon.
CORS: http://localhost:5173 and http://127.0.0.1:5173 only, in dev.
Errors: {"error": {"code": "...", "message": "..."}} with 400/413/415/422/500.
Never returns a fake success after an error, and never invents a real audit —
this sample is explicitly source="backend" only in shape; the persons/findings
are fixture data until SAM + Muse are wired in. Do NOT present this sample
as a real audit in a demo without the SAMPLE DATA labelling Raakin uses
in fixture mode, or a real masked evidence image.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
import io

MAX_BYTES = 15_000_000
MAX_DIM = 4096
MAX_MP = 16_000_000
MAX_ZONES = 20
MAX_POINTS = 100
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="Vigilens backend skeleton")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

SAMPLE = json.loads(Path(__file__).with_name("sample-audit-v0.2.json").read_text())


def err(status: int, code: str, message: str):
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


def validate_zones(raw: str):
    try:
        zones = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="INVALID_ZONES")
    if not isinstance(zones, list):
        raise HTTPException(status_code=400, detail="INVALID_ZONES")
    if len(zones) > MAX_ZONES:
        raise HTTPException(status_code=400, detail="TOO_MANY_ZONES")
    seen = set()
    for z in zones:
        if not isinstance(z, dict):
            raise HTTPException(status_code=400, detail="INVALID_ZONE")
        zid = z.get("id")
        if not isinstance(zid, str) or not zid or zid in seen:
            raise HTTPException(status_code=400, detail="INVALID_ZONE_ID")
        seen.add(zid)
        if not isinstance(z.get("name"), str) or not isinstance(z.get("hazard"), bool):
            raise HTTPException(status_code=400, detail="INVALID_ZONE")
        pts = z.get("points")
        if not isinstance(pts, list) or not (3 <= len(pts) <= MAX_POINTS):
            raise HTTPException(status_code=400, detail="INVALID_POLYGON")
        for p in pts:
            if not isinstance(p, dict):
                raise HTTPException(status_code=400, detail="INVALID_POLYGON")
            x, y = p.get("x"), p.get("y")
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise HTTPException(status_code=400, detail="INVALID_COORDINATE")
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise HTTPException(status_code=400, detail="COORDINATE_OUT_OF_RANGE")
            if x != x or y != y:  # NaN check
                raise HTTPException(status_code=400, detail="INVALID_COORDINATE")
    return zones


@app.post("/audit")
async def audit(image: UploadFile = File(...), zones: str = Form(...)):
    # Zones first: cheap validation before reading the image.
    try:
        zones_list = validate_zones(zones)
    except HTTPException as e:
        return err(400, e.detail, "Invalid zones JSON. Please check the zones and try again.")

    if image.content_type not in ALLOWED_TYPES:
        return err(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported file type. Use JPEG, PNG, or WebP.")

    data = await image.read()
    if len(data) > MAX_BYTES:
        return err(413, "IMAGE_TOO_LARGE", "Image too large. Maximum is 15 MB.")

    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
    except Exception:
        return err(422, "IMAGE_UNREADABLE", "Image readable but could not be audited.")

    if width > MAX_DIM or height > MAX_DIM or width * height > MAX_MP:
        return err(422, "IMAGE_DIMENSIONS_TOO_LARGE", "Image dimensions exceed 4096x4096 / 16 MP.")

    # TODO (real backend): SAM segmentation + Muse reasoning + deterministic
    # severity matrix + face masking go here. Until then, return the sample
    # shape with the request's zones echoed and a fresh audit_id.
    # Filter the sample to the zones actually sent, so frontend validation
    # (zone_id must be in zones or null) never fails on a sample person
    # from a zone the operator did not draw.
    out = json.loads(json.dumps(SAMPLE))
    out["audit_id"] = f"audit-{uuid.uuid4().hex[:12]}"
    out["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["image"] = {"id": f"img-{uuid.uuid4().hex[:12]}", "width": width, "height": height}
    out["zones"] = zones_list
    zone_ids = {z["id"] for z in zones_list}
    kept = []
    for person in out["persons"]:
        if person["zone_id"] is not None and person["zone_id"] not in zone_ids:
            continue
        person["findings"] = [
            f for f in person["findings"]
            if f.get("zone_id") in zone_ids or f.get("zone_id") is None
        ]
        # Recompute worst_severity from kept severity-bearing findings.
        severities = [f["severity"] for f in person["findings"] if f.get("severity")]
        order = {"Critical": 3, "Medium": 2, "Low": 1}
        person["worst_severity"] = (
            max(severities, key=lambda s: order.get(s, 0)) if severities else None
        )
        kept.append(person)
    out["persons"] = kept
    out["evidence_image"] = {
        "url": f"http://localhost:8000/evidence/{out['audit_id']}.png"
    }
    out["evidence_status"] = "masked"
    # NOTE: /evidence/<id> below returns a PLACEHOLDER image in this skeleton,
    # not a real masked image. Do not use it as demo evidence.
    return out


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "skeleton-sample-only"}


@app.get("/evidence/{audit_id}.png")
async def evidence_placeholder(audit_id: str):
    """Placeholder only: a grey image so the frontend can test overlay alignment.
    NOT a real masked image. Real face masking + serving is the next step."""
    from fastapi.responses import Response
    from PIL import ImageDraw

    img = Image.new("RGB", (1280, 720), (120, 120, 120))
    draw = ImageDraw.Draw(img)
    draw.text((40, 340), "SKELETON PLACEHOLDER - NOT REAL EVIDENCE", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
