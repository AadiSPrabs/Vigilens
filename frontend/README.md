# Vigilens Frontend

React + Vite frontend for Vigilens PPE and site-safety auditing tool.

## Setup

```bash
npm install
npm run dev
```

Runs in fixture mode by default, no backend or env file required.

## Modes

### Fixture mode (default)
- Uses bundled sample images and audit fixtures
- `VITE_AUDIT_MODE=fixture` (default)
- Fixture results only appear for matching bundled samples with preset zones
- Shows "SAMPLE DATA - not a real audit" banner

### Backend mode
- `VITE_AUDIT_MODE=backend`
- `VITE_API_BASE_URL=<backend-url>`
- Sends multipart POST to backend endpoint (path to be confirmed with backend team)
- No Meta API keys or calls from frontend

## Features

- Upload images (jpg/png/webp, max 15MB) or use bundled samples
- Draw hazard/safe zones on images with SVG overlay
- Zones persist to localStorage for user uploads only (keyed by filename+size)
- Samples use preset zones only, never read localStorage
- PPE detection: hard hat, high-visibility vest (present/absent/unknown)
- Severity: Critical (red), Medium (amber), Low (green), other values (including "High") render as grey with raw text
- Full keyboard accessibility
- Stale state detection - results cleared when image/zones change

## Testing

```bash
npm test
npm run build
```

## Swapping in real sample images

Replace files in `src/fixtures/` (sample1.png, sample2.png, sample3.png) and update `src/fixtures/index.js` with corresponding preset zones. Ensure zone polygons align with figures in the images.
