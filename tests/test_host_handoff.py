#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""host_handoff.py 回归：契约字段、确定性、过期判定、无宿主工具名、brief 输出。"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "medagentwork" / "scripts" / "host_handoff.py"
FORBIDDEN = ("subagent", "read 工具", "Cherry Studio", "PowerShell", "Bash 工具")


def load():
    spec = importlib.util.spec_from_file_location("pkg_host_handoff", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    if str(SCRIPT.parent) not in sys.path:
        sys.path.insert(0, str(SCRIPT.parent))
    spec.loader.exec_module(mod)
    return mod


def workspace(root, batch="batch001"):
    d = root / "中间产物" / batch
    d.mkdir(parents=True)
    (d / "ALL_questions.json").write_text("[{}]", encoding="utf-8")
    (d / "_ctx.md").write_text("# ctx", encoding="utf-8")
    return root


def test_build_contract_and_no_host_tool_names():
    m = load()
    with tempfile.TemporaryDirectory() as t:
        root = workspace(Path(t))
        b = m.build("batch001", "a3", root)
        assert b["schema_version"] == "1.0"
        assert b["owner"] == "MedQC" and b["stage"] == "a3"
        assert "gate_run.py" in b["gate"] and b["gate"].endswith("--stage a3")
        assert b["preflight"] and "gate_audit.py" in b["preflight"]
        assert b["write_scope"] == "report" and b["parallel_safe"] is True
        assert b["supported_levels"] == ["L2", "L1", "L0"]
        assert len(b["inputs_fingerprint"]) == 64
        assert any(i["path"].endswith("ALL_questions.json") and i["sha256"] for i in b["inputs"])
        assert b["inputs"][-1]["read"] == "by-id"
        text = json.dumps(b, ensure_ascii=False)
        for word in FORBIDDEN:
            assert word not in text, word


def test_build_is_deterministic():
    m = load()
    with tempfile.TemporaryDirectory() as t:
        root = workspace(Path(t))
        a = json.dumps(m.build("batch001", "a3", root), ensure_ascii=False, sort_keys=True)
        b = json.dumps(m.build("batch001", "a3", root), ensure_ascii=False, sort_keys=True)
        assert a == b
        assert m.build("batch001", "a2", root)["parallel_safe"] is False


def test_stale_detection_after_artifact_change():
    m = load()
    with tempfile.TemporaryDirectory() as t:
        root = workspace(Path(t))
        b = m.build("batch001", "a3", root)
        p = m.bundle_path("batch001", "a3", root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        assert m.is_stale(p, root) is False
        (root / "中间产物" / "batch001" / "ALL_questions.json").write_text("[{},{}]", encoding="utf-8")
        assert m.is_stale(p, root) is True
        assert m.is_stale(root / "nope.json", root) is None


def test_brief_cli_prints_commands():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        bundle = root / "a3.json"
        bundle.write_text(json.dumps({
            "batch": "batch001", "stage": "a3", "owner": "MedQC",
            "role_skill": "references/medqc.md", "prompt_ref": "references/prompts/MedQC_current_prompt.md",
            "ctx": "中间产物/batch001/_ctx.md", "inputs": [], "outputs": [{"path": "质检报告/batch001/A3_质检报告.json"}],
            "preflight": "python {SKILL}/scripts/gate_audit.py --batch batch001",
            "gate": "python {SKILL}/scripts/gate_run.py --batch batch001 --stage a3",
            "done": ["产物可解析", "gate exit 0"], "report_format": "三行",
            "write_scope": "report", "parallel_safe": True, "supported_levels": ["L2", "L1", "L0"],
            "inputs_fingerprint": hashlib.sha256(b"[]").hexdigest(),
        }, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "brief", "--batch", "batch001", "--stage", "a3", "--bundle", str(bundle)],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "gate_run.py" in proc.stdout and "references/medqc.md" in proc.stdout
        assert "[OK] 包完好" in proc.stdout
