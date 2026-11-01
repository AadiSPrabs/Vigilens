# Local review demo

Use only generated synthetic images. No live API/client is constructed; no spend, deploy or public bind is part of this demo.

Run `python demo_offline.py` for a complete self-contained synthetic fixture HTTP plus mock observation/report demo. It creates only temporary local journals and pixels, asserts duplicate-key behavior and export blocking, then prints a labelled summary. No model/client/account is used.

1. Create a Python3.10 virtual environment, install requirements-lock.txt, then run `sh scripts/check.sh` inside it. Tests generate their own synthetic images and temporary SQLite journals. A single existing FastAPI TestClient/httpx deprecation warning is expected.
2. Run `python run_local.py --database /tmp/vigilens-demo.sqlite --port 8000`. It binds127.0.0.1 only. GET /health must say fixture_only and real_analysis_enabled=false. Without a paired manifest, requests correctly fail FIXTURE_NOT_CONFIGURED; that is not a broken model connection.
3. For successful HTTP fixture tests, see tests/test_http_worker.py and tests/test_job_api.py. They explicitly construct a manifest paired with their generated white raster and exact zones, then exercise the API through TestClient. Do not point arbitrary worksite photos at that manifest.
4. For the offline observation/report path see test_pipeline_to_worker_to_scoped_result in tests/test_migrations.py. That test is manually authored mock PPE, never SAM output. It connects bounded rules to the worker and scoped durable storage. This path is separate from fixture /audit input.
5. For segmentation wire boundaries, tests/test_adapters.py checks request construction, completion, errors and byte limits. Nonempty wire output requires the official parser; there is no hand-written encoded mask decoder.
6. For synthetic mask coordinates/redaction see tests/test_geometry.py and tests/test_pipeline.py. Successful tests never grant privacy/export. Generated geometry is not accuracy measurement.
7. For local storage/deletion see tests/test_evidence.py. Assets are synthetic-only private test blobs, not released evidence. Scoped IDs are not authentication. Tests use temporary directories; no production deletion promise is made.
8. Stop the local server. A graceful Uvicorn process-shutdown proof has not been recorded; cooperative worker shutdown is covered in library and lifespan tests. Never leave this local review server exposed publicly.

## Not ready for a real-scene demo

Still missing: official SAM token/mask parser integration, Muse image/structured response adapter, real PPE/mask calibration, validated face/bystander privacy, authenticated principals, real-evidence release review/operator policy, deployment and billing reconciliation. No test count substitutes for these. Aadi's decisions on privacy, retention, public demo content and spend remain separate.

Journal privacy: new job/usage files are0600. Existing broadly readable files now fail startup without modification; back them up and explicitly set private permissions before reuse. Use a private parent directory. This is not encryption or public authentication. Tests generate their own files. `python scripts/socket_smoke.py` runs actual loopback HTTP with generated pixels and temporary journals, then terminates the server.
