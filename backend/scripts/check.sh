#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python -m compileall -q app.py core.py manifest.py rules.py ledger.py runner.py job_api.py pipeline.py privacy.py worker.py limits.py run_local.py adapters.py explanations.py geometry.py usage.py evidence.py sam_parser.py schemas.py access.py muse_adapter.py operations.py crops.py demo_offline.py private_sqlite.py reports.py
python -m pytest -q
