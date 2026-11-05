#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_audit.py —— 工作区门禁回执审计（防跳过第三层）。

`gate_run.py` 负责「跑门禁 + 写回执」，交付口负责「没有回执不出货」（仅 `qbank.py export-md`
路径；绕开 CLI 直接写文件属本地边界）。本脚本负责**事后复核**：把整个工作区扫一遍，看有没有
「产物在、回执不在 / 回执断了 / 产物被改过 / 签收批次缺阶段」。

用法
----
    python {SKILL}/scripts/gate_audit.py --batch batch001
    python {SKILL}/scripts/gate_audit.py --all
    python {SKILL}/scripts/gate_audit.py --all --strict      # 在途批次也要求完整链
    python {SKILL}/scripts/gate_audit.py --all --json-out reports/validate/gate_audit.json

退出码：0 = 无 FAIL（可有 WARN）；1 = 有 FAIL；2 = 参数/环境错误。

判定口径
--------
- 有交付物（`最终产物/{batch}/ALL_questions_FIXED.json` 或交付 MD）或批次已签收，却没有回执链 → FAIL `LEDGER_MISSING`；
- 在途批次没有回执 → WARN，不误伤；
- 产物存在却缺少对应阶段回执 → FAIL `STAGE_MISSING`；
- 回执阶段顺序被重排（a2→a3→a4→export 的首次出现顺序不单调）→ FAIL `STAGE_ORDER`；
- 回执记录的产物字节与磁盘不符 → FAIL `ARTIFACT_MISMATCH`（改了产物没重跑门禁）；
- 链断/序号错/内容被改/回执链损坏 → FAIL `CHAIN_BROKEN` / `SEQ_MISMATCH` / `LEDGER_CORRUPT`；
- 回执含机械判定为不适用的子门禁（SKIPPED）→ WARN；`--golden-absent` 降级 → WARN；
- 纯题库批次不要求 a5；纯复习资料批次不要求 a2/a3/a4（与 `gate_check` 的产物类型分流同源）。
- 同阶段重跑会追加新回执；审计按**每阶段最新一条**校验产物字节（旧回执是历史，仍参与链校验）。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import gate_ledger as ledger

BASE = Path.cwd()

STAGE_ORDER = {"a2": 1, "a3": 2, "a4": 3, "lv": 4, "a5": 5, "export": 6}
REQUIRED_PRE = {"a3": ["a2"], "a4": ["a3"], "lv": ["a4"], "a5": ["a4"], "export": ["a4"]}


def _configure_stdio() -> None:
    try:
        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _questions(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        data = data.get("questions")
    return data if isinstance(data, list) else None


def _schema_ge_2(path: Path) -> bool:
    data = _questions(path)
    if not data:
        return False
    for q in data:
        if not isinstance(q, dict):
            continue
        try:
            if float(str(q.get("schema_version") or "0")) >= 2.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def lv_applicable(batch: str) -> bool:
    for p in (BASE / "最终产物" / batch / "ALL_questions_FIXED.json",
              BASE / "中间产物" / batch / "ALL_questions.json"):
        if p.is_file():
            return _schema_ge_2(p)
    return False


def _glob(patterns):
    hits = []
    for pat in patterns:
        hits.extend(sorted(BASE.glob(pat)))
    out, seen = [], set()
    for p in hits:
        if p.is_file() and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            out.append(p)
    return out


def review_mds_for(subject: str):
    """主复习资料 MD。给定科目时只认该科目（避免把别科的 MD 算进本批）。"""
    if not subject:
        return _glob(["复习资料/*/*主复习资料*.md",
                      "Obsidian产物/教师重点蓝图版/*主复习资料*.md"])
    return _glob([f"复习资料/{subject}教学计划版/*主复习资料*.md",
                  f"复习资料/{subject}教师重点版/*主复习资料*.md",
                  f"Obsidian产物/教师重点蓝图版/{subject}*主复习资料*.md"])


def delivery_md_for(batch: str, types: set):
    """交付 MD 候选：qbank 生成的 ALL_questions_FIXED.md，或押题卷的 *押题*.md。

    返回 (路径 or None, 是否必须由 export 回执绑定)。
    """
    final_dir = BASE / "最终产物" / batch
    fixed_md = final_dir / "ALL_questions_FIXED.md"
    if fixed_md.is_file():
        return fixed_md, True
    if "prediction_paper" in types and final_dir.is_dir():
        alts = sorted(final_dir.glob("*押题*.md"))
        if alts:
            return alts[0], False
    return None, False


def _batch_state(batch: str) -> dict:
    try:
        import workflow_state as ws
        state, err = ws.load_state()
        if err or not isinstance(state, dict):
            return {}
        b = state.get(batch)
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _product_types(batch: str) -> set:
    state = _batch_state(batch)
    try:
        import gate_check as gc
        return set(gc.infer_product_types(batch, state))
    except Exception:
        types = set()
        if list((BASE / "最终产物" / batch).glob("ALL_questions_FIXED*.json")):
            types.add("question_bank")
        if review_mds_for(str(state.get("subject") or "")):
            types.add("review_material")
        return types or {"question_bank"}


def _latest_stamps(led) -> dict:
    out = {}
    for st in led.get("stamps") or []:
        out[st.get("stage")] = st
    return out


def _first_seq(led) -> dict:
    out = {}
    for st in led.get("stamps") or []:
        stage = st.get("stage")
        if stage not in out:
            out[stage] = st.get("seq")
    return out


def audit_batch(batch: str, strict: bool = False) -> dict:
    rec = {"batch": batch, "verdict": "PASS", "code": "OK",
           "fails": [], "warns": [], "stages": [], "ledger": str(ledger.ledger_path(batch))}
    state = _batch_state(batch)
    status = str(state.get("status") or "")
    approved = status.upper() == "APPROVED"
    subject = str(state.get("subject") or "")
    types = _product_types(batch)
    question_bearing = bool(types & {"question_bank", "prediction_paper"})
    review_bearing = "review_material" in types
    fixed = BASE / "最终产物" / batch / "ALL_questions_FIXED.json"
    delivery_md, export_required = delivery_md_for(batch, types)
    has_delivery = fixed.is_file() or delivery_md is not None

    if not ledger.BATCH_RE.match(str(batch)):
        rec["fails"].append({"code": "BATCH_NAME_INVALID",
                             "detail": f"批次目录 {batch!r} 不符合 batchNNN 命名；交付口/审计按命名识别批次"})
        return _finish(rec)

    led, err = ledger.load_ledger(batch)
    if err:
        rec["fails"].append({"code": "LEDGER_CORRUPT", "detail": err})
        return _finish(rec)
    if led is None:
        if has_delivery or approved or strict:
            rec["fails"].append({"code": "LEDGER_MISSING",
                                 "detail": "有交付物/已签收，但没有任何回执链（该批次跳过了门禁）"})
        else:
            rec["warns"].append({"code": "NO_LEDGER", "detail": "在途批次还没有回执（尚未跑门禁）"})
        return _finish(rec)

    for issue in ledger.verify_chain(led):
        rec["fails"].append({"code": issue.get("id"), "detail": issue.get("detail")})
    stamps = _latest_stamps(led)
    rec["stages"] = sorted(stamps, key=lambda s: STAGE_ORDER.get(s, 99))
    for stage, st in stamps.items():
        for issue in ledger.verify_artifacts(st):
            rec["fails"].append({"code": issue.get("id"), "detail": issue.get("detail")})
        if st.get("skipped"):
            rec["warns"].append({"code": "STAMP_WITH_SKIPS",
                                 "detail": f"{stage} 含 SKIPPED 子门禁：" +
                                           ", ".join(str(x.get("id")) for x in st["skipped"])})
    if any((st.get("flags") or {}).get("golden_absent") for st in stamps.values()):
        rec["warns"].append({"code": "GOLDEN_ABSENT",
                             "detail": "回执记录了 --golden-absent 降级（该批次无金标准兜底）"})

    first_seq = _first_seq(led)
    for stage, preds in REQUIRED_PRE.items():
        if stage not in first_seq:
            continue
        if stage in ("a2", "a3", "a4", "lv") and not question_bearing:
            continue  # 纯复习资料批次没有题库阶段
        for pred in preds:
            if pred in ("a2", "a3", "a4") and not question_bearing:
                continue
            if pred not in first_seq:
                rec["fails"].append({"code": "STAGE_MISSING",
                                     "detail": f"{stage} 回执存在但缺少前置 {pred}（跳过/伪造）"})
            elif first_seq[pred] > first_seq[stage]:
                rec["fails"].append({"code": "STAGE_ORDER",
                                     "detail": f"阶段顺序错误：{pred} 首次回执 seq={first_seq[pred]} 晚于 {stage}={first_seq[stage]}"})

    required = set()
    if (BASE / "中间产物" / batch / "ALL_questions.json").is_file():
        required.add("a2")
    if (BASE / "质检报告" / batch / "A3_质检报告.json").is_file() or \
            (BASE / "质检报告" / f"{batch}_质检报告.json").is_file():
        required.add("a3")
    if fixed.is_file():
        required.add("a4")
        if lv_applicable(batch):
            required.add("lv")
    if export_required:
        required.add("export")
    if review_bearing and review_mds_for(subject):
        required.add("a5")
    if approved:
        if question_bearing:
            required |= {"a2", "a3", "a4"}
        if fixed.is_file() and lv_applicable(batch):
            required.add("lv")
        if export_required:
            required.add("export")
        if review_bearing and review_mds_for(subject):
            required.add("a5")
    if strict and has_delivery:
        required.add("export" if export_required else "a4")
    for stage in sorted(required, key=lambda s: STAGE_ORDER.get(s, 99)):
        if stage not in stamps:
            rec["fails"].append({"code": "STAGE_MISSING",
                                 "detail": f"产物已存在但回执链缺少 {stage} 阶段（该门禁被跳过）"})

    st_a4 = stamps.get("a4")
    if st_a4 and fixed.is_file():
        covered = {Path(a["path"]).as_posix() for a in st_a4.get("artifacts") or ()}
        if ledger.rel(fixed) not in covered:
            rec["fails"].append({"code": "ARTIFACT_NOT_COVERED",
                                 "detail": f"a4 回执未覆盖交付 JSON {ledger.rel(fixed)}"})
    st_ex = stamps.get("export")
    if st_ex:
        covered = {Path(a["path"]).as_posix() for a in st_ex.get("artifacts") or ()}
        if delivery_md and ledger.rel(delivery_md) not in covered and export_required:
            rec["fails"].append({"code": "ARTIFACT_NOT_COVERED",
                                 "detail": "export 回执未覆盖交付 MD（MD 被重写/未走 export-md）"})
    if delivery_md and delivery_md.name != "ALL_questions_FIXED.md":
        covered = any(ledger.rel(delivery_md) in
                      {Path(a["path"]).as_posix() for a in st.get("artifacts") or ()}
                      for st in stamps.values())
        if not covered:
            rec["warns"].append({"code": "PREDICTION_MD_UNBOUND",
                                 "detail": f"押题卷交付 MD {delivery_md.name} 未被任何回执绑定（非 qbank 生成路径）"})
    if approved and question_bearing and fixed.is_file() and delivery_md is None:
        rec["fails"].append({"code": "MISSING_DELIVERY_MD",
                             "detail": "签收批次有题库 JSON 但缺少交付 MD（应跑 qbank.py export-md，押题卷为 *押题*.md）"})
    return _finish(rec)


def _finish(rec: dict) -> dict:
    if rec["fails"]:
        rec["verdict"] = "FAIL"
        rec["code"] = rec["fails"][0].get("code") or rec["fails"][0].get("id") or "FAIL"
    elif rec["warns"]:
        rec["verdict"] = "WARN"
        rec["code"] = rec["warns"][0].get("code") or "WARN"
    else:
        rec["verdict"], rec["code"] = "PASS", "OK"
    return rec


def discover_batches() -> list:
    root = BASE / "最终产物"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))


def main(argv=None) -> int:
    _configure_stdio()
    ap = argparse.ArgumentParser(description="工作区门禁回执审计（gate_audit，v2.5.0）")
    ap.add_argument("--batch", "-b", default="", help="只审计一个批次")
    ap.add_argument("--all", action="store_true", help="审计 最终产物/ 下全部批次（默认）")
    ap.add_argument("--strict", action="store_true", help="在途批次也要求完整回执链")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    if args.batch:
        batches = [args.batch]
    else:
        batches = discover_batches()
    if not batches:
        print("（没有发现需要审计的批次：最终产物/ 为空）")
        return 0

    results = [audit_batch(b, strict=args.strict) for b in batches]
    fails = [r for r in results if r["verdict"] == "FAIL"]
    warns = [r for r in results if r["verdict"] == "WARN"]
    print(f"=== 门禁回执审计（{len(results)} 个批次）===")
    for r in results:
        mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[r["verdict"]]
        print(f"  [{mark}] {r['batch']}  stages={','.join(r['stages']) or '-'}  {r['code']}")
        for f in r["fails"]:
            print(f"         ✗ {f.get('code')}: {f.get('detail')}")
        for w in r["warns"]:
            print(f"         ! {w.get('code')}: {w.get('detail')}")
    summary = {"ts": datetime.now().isoformat(timespec="seconds"),
               "total": len(results), "pass": len(results) - len(fails) - len(warns),
               "warn": len(warns), "fail": len(fails),
               "verdict": "FAIL" if fails else ("WARN" if warns else "PASS"),
               "batches": results}
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== 结论: {summary['verdict']}（PASS {summary['pass']} / WARN {summary['warn']} / FAIL {summary['fail']}）===")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
