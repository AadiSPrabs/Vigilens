# Vigilens Frontend

## Stack
- React + Vite + JavaScript + plain CSS
- Testing: Vitest + @testing-library/react (dev only)

## Environment Variables
- `VITE_AUDIT_MODE` (fixture|backend) — defaults to fixture mode if not set. In fixture mode only bundled samples work. In backend mode posts to API.
- `VITE_API_BASE_URL` — base URL for backend (default: `http://localhost:8000`). Requests go to `{VITE_API_BASE_URL}/audit`.

## Running Modes

### Fixture Mode (default)
1. Install dependencies: `npm install`
2. Run dev server: `npm run dev`
3. Use one of the bundled sample images with preset zones. Fixture results only load for matching bundled samples with preset zones.

### Local Backend Mode
1. Set environment variables (e.g. `.env`):
   ```
   VITE_AUDIT_MODE=backend
   VITE_API_BASE_URL=http://localhost:8000
   ```
2. Ensure your local backend implements `POST /audit` per `CONTRACT.md` (v0.2-local-draft) and `GET /health`.
3. Start the frontend: `npm run dev`
4. Upload an image and draw zones; requests use `FormData` with `image` and `zones` (JSON string) and `Idempotency-Key` header. No manual `Content-Type` is set.

## Contract Pairing Test Assets
Contract test assets are in `src/fixtures/contract/`:
- `contract-sample.png` — real binary raster PNG (1280x720) for backend pairing
- `contract-sample.svg` — SVG overlay reference
- `contract-zones.json` — zones with exact structure (zone-1 Crane Zone hazard true, zone-2 Storage Yard hazard false)
- `sample-audit-v0_2.json` — sample audit response
- `index.js`, `README.md`

To pair with a local backend manifest, use `contract-sample.png` with `contract-zones.json` and expect the contract sample audit shape. The UI includes a backend-only "Contract test (backend pairing)" picker.

## Demo Recording Note
**Important:** Use licensed, real-world photos for the final hackathon demo recording. The bundled samples are synthetic and intended for development/testing only.
