#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁回执链（gate ledger）—— 防跳过层的原语。

要解决的问题
------------
门禁脚本只在「有人调用它」时生效。换一个 agent 软件、换一个模型，完全可以跳过
`references/runbook.md` 第 3 节的命令，直接把文件写进 `最终产物/` —— 本地没有消费方
校验，事后也查不出来。**提示词不是约束**；本模块把「门禁执行」变成交付物自己的属性：

- 每个阶段 PASS 后写一条回执：产物字节 sha256 + 门禁执行的字节摘要 + 门禁清单；
- 回执用 `chain_prev` 链式相连（head 为最后一条），删一条、改一条、插一条都会断链；
- 交付口（`qbank.py export-md` 写 `最终产物/`）与 `gate_audit.py` 都先验回执。

回执位置与形状
--------------
    最终产物/{batch}/_gate_ledger.json
    {"schema_version": "1.0", "batch": "batch001", "created_at": "...",
     "tool": "gate_run@2.6.0", "head": "sha256:...",
     "stamps": [
       {"seq": 1, "stage": "a2", "verdict": "PASS", "provenance": "gate_run",
        "ts": "...", "tool": "gate_run@2.6.0",
        "artifacts": [{"path": "中间产物/batch001/ALL_questions.json",
                       "sha256": "...", "bytes": 123}],
        "gate_reports": [{"path": "reports/validate/...", "sha256": "..."}],
        "gates": [{"id": "GATE-A2", "argv": ["...", "..."], "rc": 0, "stdout_sha256": "..."}],
        "skipped": [{"id": "KEYPOINT", "reason": "无教师重点输入"}],
        "flags": {}, "note": null, "chain_prev": null, "hash": "sha256:..."}
     ]}

职责边界（诚实声明，别指望它做不到的事）
----------------------------------------
1. 回执能证明「产物与一次门禁执行绑定」；**不能**证明执行者不可伪造 —— 有 shell 的
   agent 理论上能自己 append。它能做到的是：跳过必留痕（缺回执/断链）、交付口必拒收、
   审计可复核。
2. 本模块不做判定、不跑门禁、不写 `workflow_state.json`；只负责「记录 + 验真」。
3. v2.5.0 起回执对**所有批次**强制（分享版不存在历史批次豁免：升级前已在途的批次，
   重跑一次确定性门禁即可，门禁本身是幂等的）。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BASE = Path.cwd()

SCHEMA_VERSION = "1.0"
LEDGER_NAME = "_gate_ledger.json"
STAGES = ("a2", "a3", "a4", "lv", "a5", "export")

# 阶段 → 该阶段必须被回执覆盖的交付物（相对工作区，{batch} 占位）。
# a5/export 的产物路径依赖科目/MD 名，由 gate_run / export-md 显式传入并绑定；这里只做「已知路径」的机械判定。
_STAGE_ARTIFACTS = {
    "a2": ["中间产物/{batch}/ALL_questions.json"],
    "a3": ["质检报告/{batch}/A3_质检报告.json", "质检报告/{batch}_质检报告.json"],
    "a4": ["最终产物/{batch}/ALL_questions_FIXED.json"],
    "lv": ["最终产物/{batch}/ALL_questions_FIXED.json"],
    "export": ["最终产物/{batch}/ALL_questions_FIXED.md", "最终产物/{batch}/ALL_questions_FIXED.json"],
}

# 判定优先级：按此顺序取第一个命中的 FAIL code。
FAIL_CODES = (
    "LEDGER_CORRUPT",
    "CHAIN_BROKEN",
    "SEQ_MISMATCH",
    "LEDGER_MISSING",
    "STAGE_MISSING",
    "ARTIFACT_MISSING",
    "ARTIFACT_MISMATCH",
    "ARTIFACT_NOT_COVERED",
)

BATCH_RE = re.compile(r"^batch\d{3}(?:-[A-Za-z0-9]+)?$")


def _configure_stdio() -> None:
    """Windows 控制台 GBK 下也能稳定输出中文/emoji。"""
    try:
        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def batch_number(batch_id: str):
    m = re.search(r"(\d{3})", str(batch_id or ""))
    return int(m.group(1)) if m else None


def batch_id_from_path(path) -> str | None:
    """从路径里识别 <产物目录>/{batch} 形态的批次号。识别不到返回 None。"""
    parts = Path(path).parts
    for i, part in enumerate(parts[:-1]):
        if part in ("最终产物", "中间产物", "质检报告") and BATCH_RE.match(parts[i + 1]):
            return parts[i + 1]
    return None


def ledger_path(batch_id: str, base: Path | None = None) -> Path:
    return Path(base or BASE) / "最终产物" / batch_id / LEDGER_NAME


def rel(path, base: Path | None = None) -> str:
    """尽量转成工作区相对路径（POSIX 分隔符）；不在工作区内则原样返回。"""
    p = Path(path)
    try:
        return p.resolve().relative_to(Path(base or BASE).resolve()).as_posix()
    except Exception:
        return p.as_posix()


def _norm_path(path) -> str:
    """回执内一律记录 POSIX 路径：Windows 写入的反斜杠在 Linux CI 上会被当成文件名。"""
    p = Path(path)
    if p.is_absolute():
        return rel(p)
    return p.as_posix()


def file_sha256(path) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stamp_hash(stamp: dict) -> str:
    body = {k: v for k, v in stamp.items() if k != "hash"}
    return "sha256:" + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def new_ledger(batch_id: str, tool: str = "gate_run") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "batch": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "head": None,
        "stamps": [],
    }


def load_ledger(batch_id: str, base: Path | None = None, path=None):
    """返回 (ledger, error)。文件不存在 → (None, None)；不可解析 → (None, 错误说明)。"""
    p = Path(path) if path else ledger_path(batch_id, base)
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"{p}: {type(exc).__name__}: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("stamps"), list):
        return None, f"{p}: 不是合法的回执链（缺少 stamps 数组）"
    if str(data.get("batch") or "") != str(batch_id or ""):
        return None, f"{p}: 回执链 batch={data.get('batch')!r} 与请求 {batch_id!r} 不符（缺 batch 字段也算，防重放）"
    if any(not isinstance(st, dict) for st in data["stamps"]):
        return None, f"{p}: 回执链含非对象条目（stamps 必须是对象数组）"
    return data, None


def write_ledger(ledger: dict, base: Path | None = None, path=None) -> str:
    p = Path(path) if path else ledger_path(ledger.get("batch", ""), base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))
    return str(p)


def expected_artifacts(batch_id: str, stage: str, base: Path | None = None):
    """该阶段「应当被回执覆盖」的已知交付物（只返回存在的；都不存在返回空）。"""
    out = []
    for pat in _STAGE_ARTIFACTS.get(stage, []):
        p = Path(base or BASE) / pat.format(batch=batch_id)
        if p.exists():
            out.append(p)
    return out


def append_stamp(ledger: dict, stage: str, artifacts=(), gate_reports=(), gates=(),
                 skipped=(), flags=None, provenance="gate_run", tool="gate_run",
                 note=None, ts=None) -> dict:
    """追加一条回执并更新 head。artifacts / gate_reports 接受路径字符串或 Path。"""
    if stage not in STAGES:
        raise ValueError(f"未知阶段: {stage!r}（允许 {STAGES}）")
    arts = []
    for a in artifacts or ():
        p = Path(a)
        arts.append({
            "path": _norm_path(a),
            "sha256": file_sha256(p),
            "bytes": p.stat().st_size if p.is_file() else None,
        })
    reps = []
    for r in gate_reports or ():
        p = Path(r)
        if p.is_file():
            reps.append({"path": _norm_path(r), "sha256": file_sha256(p)})
    prev = ledger["stamps"][-1] if ledger["stamps"] else None
    stamp = {
        "seq": len(ledger["stamps"]) + 1,
        "stage": stage,
        "verdict": "PASS",
        "provenance": provenance,
        "ts": ts or datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "artifacts": arts,
        "gate_reports": reps,
        "gates": list(gates or ()),
        "skipped": list(skipped or ()),
        "flags": dict(flags or {}),
        "note": note,
        "chain_prev": prev.get("hash") if prev else None,
    }
    stamp["hash"] = _stamp_hash(stamp)
    ledger["stamps"].append(stamp)
    ledger["head"] = stamp["hash"]
    return stamp


def verify_chain(ledger: dict):
    """校验回执链自洽：顺序号、每条自身哈希、chain_prev 衔接、head。返回问题列表。"""
    issues = []
    stamps = ledger.get("stamps") or []
    prev_hash = None
    for i, st in enumerate(stamps, 1):
        where = f"#{i}({st.get('stage')})"
        if st.get("seq") != i:
            issues.append({"id": "SEQ_MISMATCH", "detail": f"{where} seq={st.get('seq')} 期望 {i}"})
        if st.get("chain_prev") != prev_hash:
            issues.append({"id": "CHAIN_BROKEN",
                           "detail": f"{where} chain_prev={st.get('chain_prev')} 期望 {prev_hash}"})
        if st.get("hash") != _stamp_hash(st):
            issues.append({"id": "CHAIN_BROKEN", "detail": f"{where} 内容被改动（哈希不符）"})
        prev_hash = st.get("hash")
    if stamps and ledger.get("head") != stamps[-1].get("hash"):
        issues.append({"id": "CHAIN_BROKEN", "detail": "head 与最后一条回执不符"})
    return issues


def verify_artifacts(stamp: dict, base: Path | None = None):
    """校验某条回执里记录的产物是否仍是当时那份（字节级）。返回问题列表。"""
    issues = []
    for art in stamp.get("artifacts") or ():
        p = Path(base or BASE) / art["path"] if not Path(art["path"]).is_absolute() else Path(art["path"])
        if not p.is_file():
            issues.append({"id": "ARTIFACT_MISSING", "detail": f"{art['path']} 不存在（回执已记录）"})
            continue
        actual = file_sha256(p)
        if actual != art.get("sha256"):
            issues.append({"id": "ARTIFACT_MISMATCH",
                           "detail": f"{art['path']} sha256={str(actual)[:12]}… 回执={str(art.get('sha256'))[:12]}…"
                                     "（产物在此之后被改过，需重跑该阶段门禁）"})
    return issues


def find_stamp(ledger: dict, stage: str):
    """取该阶段最后一条回执（同阶段重跑时以最新为准）。"""
    hits = [s for s in ledger.get("stamps") or [] if s.get("stage") == stage]
    return hits[-1] if hits else None


def verify(batch_id: str, stage: str, base: Path | None = None, path=None,
           require_artifacts=None) -> dict:
    """验真一个阶段的回执。返回结构化结论（不改任何文件）。

    verdict: PASS / WARN（回执存在但含 skipped 子门禁）/ FAIL
    """
    report = {
        "batch": batch_id,
        "stage": stage,
        "verdict": "PASS",
        "code": "STAMP_OK",
        "ledger": None,
        "stamp_seq": None,
        "checks": [],
        "issues": [],
        "warnings": [],
        "skipped": [],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }

    def add(cid, status, detail):
        report["checks"].append({"id": cid, "status": status, "detail": detail})

    ledger, err = load_ledger(batch_id, base, path)
    report["ledger"] = str(Path(path) if path else ledger_path(batch_id, base))
    if err:
        report["verdict"], report["code"] = "FAIL", "LEDGER_CORRUPT"
        add("ledger", "FAIL", err)
        return report
    if ledger is None:
        report["verdict"], report["code"] = "FAIL", "LEDGER_MISSING"
        add("ledger", "FAIL", f"没有回执链：{report['ledger']}（该批次跳过了门禁）")
        return report
    add("ledger", "PASS", f"{len(ledger['stamps'])} 条回执")

    chain_issues = verify_chain(ledger)
    report["issues"] += chain_issues
    add("chain", "FAIL" if chain_issues else "PASS",
        "; ".join(i["detail"] for i in chain_issues) or "链完整")

    stamp = find_stamp(ledger, stage)
    if stamp is None:
        report["verdict"], report["code"] = "FAIL", "STAGE_MISSING"
        add("stage", "FAIL", f"回执链里没有 {stage} 阶段（跳过了该门禁）")
        return report
    report["stamp_seq"] = stamp.get("seq")
    add("stage", "PASS", f"seq={stamp.get('seq')} provenance={stamp.get('provenance')}")

    art_issues = verify_artifacts(stamp, base)
    report["issues"] += art_issues
    add("artifacts", "FAIL" if art_issues else "PASS",
        "; ".join(i["detail"] for i in art_issues) or f"{len(stamp.get('artifacts') or [])} 个产物字节一致")

    if require_artifacts:
        covered = {Path(a["path"]).as_posix() for a in stamp.get("artifacts") or ()}
        missing = [x for x in require_artifacts if rel(x, base) not in covered]
        if missing:
            report["issues"].append({"id": "ARTIFACT_NOT_COVERED",
                                     "detail": "回执未覆盖: " + ", ".join(missing)})
            add("coverage", "FAIL", "回执未覆盖: " + ", ".join(missing))
        else:
            add("coverage", "PASS", "目标产物已被回执覆盖")

    skipped = stamp.get("skipped") or []
    report["skipped"] = [s.get("id") for s in skipped if isinstance(s, dict)]
    if skipped:
        report["warnings"] += [f"子门禁 SKIPPED：{s.get('id')}（{s.get('reason')}）"
                               for s in skipped if isinstance(s, dict)]
        add("skipped", "WARN", "存在机械判定为不适用的子门禁（不算 PASS，但允许继续）")

    hard = [i for i in report["issues"] if i["id"] in FAIL_CODES]
    if hard:
        report["verdict"] = "FAIL"
        report["code"] = next(c for c in FAIL_CODES if any(i["id"] == c for i in hard))
        return report
    if skipped:
        report["verdict"], report["code"] = "WARN", "STAMP_WITH_SKIPS"
    return report


def required_for(batch_id: str) -> bool:
    """该批次是否属于「必须有回执」的范围。分享版对所有批次强制（v2.5.0 起）。"""
    return bool(batch_id)


def _cmd(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="查看/校验批次门禁回执链")
    ap.add_argument("action", choices=["show", "verify"])
    ap.add_argument("--batch", "-b", required=True)
    ap.add_argument("--stage", "-s", default=None, choices=list(STAGES))
    ap.add_argument("--artifact", "-a", action="append", default=[], help="要求回执覆盖的产物路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    _configure_stdio()
    if args.action == "verify":
        if not args.stage:
            ap.error("verify 需要 --stage")
        r = verify(args.batch, args.stage, require_artifacts=args.artifact)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json
              else f"{args.batch}/{args.stage}: {r['verdict']} {r['code']}")
        return 0 if r["verdict"] != "FAIL" else 1
    ledger, err = load_ledger(args.batch)
    if err or ledger is None:
        print(f"[ERROR] {err or '没有回执链'}")
        return 2
    if args.stage:
        st = find_stamp(ledger, args.stage)
        print(json.dumps(st, ensure_ascii=False, indent=2) if st else f"没有 {args.stage} 回执")
        return 0 if st else 1
    rows = [{"seq": s["seq"], "stage": s["stage"], "ts": s["ts"], "provenance": s["provenance"],
             "artifacts": [a["path"] for a in s.get("artifacts") or ()],
             "skipped": [x.get("id") for x in s.get("skipped") or ()]}
            for s in ledger["stamps"]]
    print(json.dumps({"batch": args.batch, "head": ledger["head"], "stamps": rows},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cmd())
