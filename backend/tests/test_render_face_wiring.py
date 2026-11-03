"""Render boot wires the bundled pinned YuNet model only when VIGILENS_FACE_MODEL_PATH is unset."""
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_render
from fresh_review.face_proposals import MODEL_SHA256

BUNDLED = Path(run_render.__file__).resolve().parent / 'models' / 'face_detection_yunet_2023mar.onnx'


def test_bundled_model_matches_pin():
    assert hashlib.sha256(BUNDLED.read_bytes()).hexdigest() == MODEL_SHA256


def test_default_wires_bundled_model(monkeypatch):
    monkeypatch.delenv('VIGILENS_FACE_MODEL_PATH', raising=False)
    s = SimpleNamespace()
    run_render._wire_face_proposals(s)
    assert Path(s.face_proposal_model_path) == BUNDLED


def test_env_path_wins(monkeypatch):
    monkeypatch.setenv('VIGILENS_FACE_MODEL_PATH', '/x/model.onnx')
    s = SimpleNamespace()
    run_render._wire_face_proposals(s)
    assert s.face_proposal_model_path == '/x/model.onnx'
