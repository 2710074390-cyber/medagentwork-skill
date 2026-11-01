import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/medagentwork/scripts/quality_gate.py"
POLICY = ROOT / "skills/medagentwork/scripts/quality_policy.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("package_quality_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    spec.loader.exec_module(module)
    return module


def test_policy_validates():
    result = subprocess.run([sys.executable, str(POLICY), "--validate"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0


def test_r3_requires_enforce_release_profile(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--stage", "r3", "--batch", "batch999",
                             "--profile", "pilot", "--mode", "advisory", "--out", str(tmp_path / "r.json")],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    assert "R3 强制要求" in result.stderr


def test_missing_bundle_capabilities_block_enforce():
    gate = load_gate()
    checks = [gate.bundled_or_skip("r3.site_freshness", "线上新鲜度")]
    status, blocking, _ = gate.aggregate(checks, "enforce")
    assert status == "BLOCKED"
    assert blocking


def test_input_hash_is_current():
    gate = load_gate()
    p = ROOT / "skills/medagentwork/scripts/quality_gate.py"
    assert gate.sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_product_scope_isolated(tmp_path, monkeypatch):
    gate = load_gate()
    state = {"batch999": {"subject": "神经病学", "product_types": ["question_bank"]}}
    (tmp_path / "workflow_state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(gate, "BASE", tmp_path)
    assert gate.infer_batch_products("batch999") == {"question_bank"}
