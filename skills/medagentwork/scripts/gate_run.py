#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_run.py —— 阶段门禁的**唯一执行入口**（v2.5.0 引入防跳过层 · 当前 v2.6.0）。

为什么存在
----------
`references/runbook.md` 第 3 节列的是「每个阶段转换前强制执行」的命令。但只要命令是
散落在提示词里的，就总有 agent/模型/宿主软件「不按规则来」：跳过 A3 直接写 A4 产物、
少跑一个门禁、跑完又改产物。**提示词不是约束**。

本脚本把阶段门禁收窄为单一执行面：

1. **消费前验真（preflight）**：跑某阶段前，先验所有前置阶段回执；缺回执 / 断链 /
   产物字节不符 → 执行前就 `BLOCKED`，并给出「下一步命令」；
2. **执行确定性门禁**：按阶段声明跑 `validate_options / gate_check / check_*`；
3. **PASS 才写回执**：把「产物字节 sha256 + 门禁执行摘要」写进
   `最终产物/{batch}/_gate_ledger.json`，用 `chain_prev` 链式相连（`gate_ledger.py`）；
4. **交付口验真**：`qbank.py export-md` 往 `最终产物/{batch}/` 写交付 MD 时，没有有效
   A2/A3/A4 回执直接拒绝 —— 这是本层与宿主无关的硬闸（不依赖任何宿主 hook）。

覆盖阶段（防跳过链）
--------------------
`a2`（出题）→ `a3`（质检）→ `a4`（修复）→ `lv`（HC-24，schema 2.0+）→ `a5`（复习资料）。
`final` **不在回执链内**：终审门禁读的是 `workflow_state` 自述字段（`final_review.json_valid`
等），本 skill 的流程不机械产生这些字段，把它做成回执前置会让诚实用户死锁；它仍可用
`gate_check.py --batch B --stage final` 手动跑，属于质量汇总而非交付闸门。

用法
----
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage a2
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage a3
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage a4
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage lv
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage a5 [--subject 神经病学]
    python {SKILL}/scripts/gate_run.py --batch batch001 --stage all   # 按适用阶段顺序跑完

退出码：0 = PASS 且已写回执 / 机械判定 NOT_APPLICABLE；1 = BLOCKED；2 = 用法错误。

边界（诚实声明）
----------------
- 本地无法 100% 阻止伪造：有 shell 的 agent 能自己 append 回执、也能绕开 CLI 直接写文件。
  目标是把「跳过」变成**必留痕（缺回执/断链/字节不符）+ 交付口拒收（走 export-md 的路径）
  + 可审计（gate_audit）**。
- `--dry-run` / `--no-stamp` 只跑门禁不写回执，产物因此**无法交付**（交付口会拒绝）。
- 阶段适用性由产物/状态机械判定（与 `gate_check.infer_product_types` 同源）：
  纯复习资料批次不适用 a2/a3/a4/lv；纯题库批次不适用 a5。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import gate_ledger as ledger

BASE = Path.cwd()
SCRIPTS = Path(__file__).resolve().parent
TOOL = "gate_run@2.6.0"
STAGES = ("a2", "a3", "a4", "lv", "a5")
STAGE_LABEL = {
    "a2": "GATE-A2（题库校验）",
    "a3": "GATE-A3（质检报告）",
    "a4": "GATE-A4（修复产物）",
    "lv": "LV（HC-24 学习价值层）",
    "a5": "GATE-A5（复习资料：详细度/视觉/重点覆盖）",
}


def _configure_stdio() -> None:
    try:
        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── 批次信息（机械读取，不问 agent） ──────────────────────────────────────────

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


def subject_for(batch: str, override: str = "") -> str:
    if override:
        return override
    return str(_batch_state(batch).get("subject") or "")


def product_types(batch: str) -> set:
    """与 gate_check.infer_product_types 同源（优先 import，失败时本地兜底）。"""
    state = _batch_state(batch)
    try:
        import gate_check as gc
        return set(gc.infer_product_types(batch, state))
    except Exception:
        explicit = state.get("product_types")
        if isinstance(explicit, str):
            explicit = [explicit]
        if isinstance(explicit, (list, tuple, set)):
            picked = {str(x).strip() for x in explicit
                      if str(x).strip() in {"question_bank", "prediction_paper", "review_material"}}
            if picked:
                return picked
        types = set()
        if list((BASE / "最终产物" / batch).glob("ALL_questions_FIXED*.json")):
            types.add("question_bank")
        if review_mds_for(str(state.get("subject") or "")):
            types.add("review_material")
        return types or {"question_bank"}


def is_question_bearing(batch: str) -> bool:
    return bool(product_types(batch) & {"question_bank", "prediction_paper"})


def is_review_bearing(batch: str) -> bool:
    return "review_material" in product_types(batch)


def _load_questions(path: Path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        data = data.get("questions")
    return data if isinstance(data, list) else None


def lv_applicable(batch: str) -> bool:
    """HC-24 只对 schema_version>=2.0 的题库生效；按产物机械判定（不是 agent 自报）。"""
    if not is_question_bearing(batch):
        return False
    for p in (BASE / "最终产物" / batch / "ALL_questions_FIXED.json",
              BASE / "中间产物" / batch / "ALL_questions.json"):
        data = _load_questions(p) if p.exists() else None
        if data:
            for q in data:
                try:
                    if float(str(q.get("schema_version") or "0")) >= 2.0:
                        return True
                except (TypeError, ValueError):
                    continue
            return False
    return True  # 读不到产物时 fail-closed：要求 lv（真有问题会先卡在更早的门禁）


def _glob(patterns):
    hits = []
    for pat in patterns:
        hits.extend(sorted(BASE.glob(pat)))
    seen, out = set(), []
    for p in hits:
        rp = str(p.resolve())
        if rp not in seen and p.is_file():
            seen.add(rp)
            out.append(p)
    return out


def keypoints_for(subject: str):
    if not subject:
        return []
    return _glob([f"输入素材/{subject}/*教师重点*.md", f"输入素材/{subject}/*重点*.md"])


def review_mds_for(subject: str):
    """主复习资料 MD。给定科目时只认该科目（避免把别科的 MD 绑进本批回执）。"""
    if not subject:
        return _glob(["复习资料/*/*主复习资料*.md",
                      "Obsidian产物/教师重点蓝图版/*主复习资料*.md"])
    return _glob([
        f"复习资料/{subject}教学计划版/*主复习资料*.md",
        f"复习资料/{subject}教师重点版/*主复习资料*.md",
        f"Obsidian产物/教师重点蓝图版/{subject}*主复习资料*.md",
    ])


# ── 状态步骤机械补写（gate_check 的 A3/A4 需要 steps.AGENT3/AGENT4） ──────────

def sync_state_steps(batch: str) -> None:
    """按磁盘上的产物补写 workflow_state 的阶段步骤（只补缺失项，不改已有记录）。

    为什么由 gate_run 做：`gate_check` 的 A3/A4 门禁要求 `steps.AGENT3/AGENT4` 存在，
    但本 skill 的流程是「各角色直接写文件」，没有任何文档/CLI 保证步骤被登记。
    产物存在 = 该阶段已产出，这是机械事实；由唯一执行面补写，避免诚实用户被卡死。
    只写状态簿记，不改变任何门禁判定。
    """
    try:
        import workflow_state as ws
        state, err = ws.load_state()
        if err or not isinstance(state, dict):
            return
        b = state.get(batch)
        if not isinstance(b, dict) or str(b.get("status", "")).upper() == "APPROVED":
            return
        steps = b.get("steps")
        if not isinstance(steps, dict):
            steps = {}
            b["steps"] = steps
        candidates = [
            ("AGENT2", BASE / "中间产物" / batch / "ALL_questions.json"),
            ("AGENT3", BASE / "质检报告" / batch / "A3_质检报告.json"),
        ]
        trace = sorted((BASE / "最终产物" / batch).glob("*追溯日志*.json")) \
            if (BASE / "最终产物" / batch).is_dir() else []
        if trace:
            candidates.append(("AGENT4", trace[0]))
        subject = str(b.get("subject") or "")
        mds = review_mds_for(subject) if subject else []
        if mds:
            candidates.append(("AGENT5", mds[0]))
        changed = False
        for key, path in candidates:
            if key in steps or not Path(path).is_file():
                continue
            md5 = hashlib.md5(Path(path).read_bytes()).hexdigest()
            ws.add_lineage(state, batch, key.lower(), str(path), md5,
                           model="gate_run(sync)", prompt_version="unknown")
            changed = True
        if changed:
            ws.save_state(state)
            print(f"  [STATE] 已按产物补写步骤记录：{', '.join(k for k, p in candidates if Path(p).is_file())}")
    except Exception as exc:  # 状态簿记失败不应改变门禁结论，但要可见
        print(f"  [STATE] 步骤补写失败（忽略）：{exc}", file=sys.stderr)


# ── 门禁命令（阶段声明表） ───────────────────────────────────────────────────

def _gate(gate_id: str, script: str, args, skip_rc=(), report=None) -> dict:
    return {"id": gate_id,
            "argv": [sys.executable, str(SCRIPTS / script), *[str(a) for a in args]],
            "skip_rc": set(skip_rc),
            "report": str(report) if report else None}


def _a2(batch, subject, args):
    q = BASE / "中间产物" / batch / "ALL_questions.json"
    return {"gates": [_gate("GATE-A2", "validate_options.py", ["--batch", batch, "--mode", "full"])],
            "artifacts": [q], "reports": [], "skipped": []}


def _a3(batch, subject, args):
    report = BASE / "质检报告" / batch / "A3_质检报告.json"
    return {"gates": [_gate("GATE-A3", "gate_check.py", ["--batch", batch, "--stage", "agent3_done"])],
            "artifacts": [report], "reports": [], "skipped": []}


def _a4(batch, subject, args):
    fixed = BASE / "最终产物" / batch / "ALL_questions_FIXED.json"
    return {"gates": [_gate("GATE-A4", "gate_check.py", ["--batch", batch, "--stage", "agent4_done"])],
            "artifacts": [fixed], "reports": [], "skipped": []}


def _lv(batch, subject, args):
    fixed = BASE / "最终产物" / batch / "ALL_questions_FIXED.json"
    report = BASE / "reports" / "validate" / f"learning_value_{batch}_gate.json"
    return {"gates": [_gate("LV-HC24", "check_learning_value.py",
                            ["--file", fixed, "--batch", batch, "--out", report],
                            report=report)],
            "artifacts": [fixed], "reports": [report], "skipped": []}


def _a5(batch, subject, args):
    if not subject:
        return {"error": "REVIEW_SUBJECT_MISSING",
                "hint": "工作区状态里没有该批次 subject；传 --subject {科目}，或先登记批次"}
    mds = [Path(p) for p in args.review] if args.review else review_mds_for(subject)
    mds = [p for p in mds if p.is_file()]
    if not mds:
        return {"error": "REVIEW_MISSING",
                "hint": "没有找到主复习资料 MD（复习资料/{科目}*/ 或 Obsidian产物/教师重点蓝图版/）；先跑 MedReview 生成"}
    gates, reports = [], []
    for md in mds:
        stem = md.stem
        detail = BASE / "reports" / "validate" / f"review_detail_{stem}.json"
        visual = BASE / "reports" / "validate" / f"review_visual_{stem}.json"
        gates.append(_gate("HC26-REVIEW-DETAIL", "check_review_detail.py",
                           ["--md", md, "--mode", "auto", "--profile", "release_teacher_keypoint",
                            "--json-out", detail], report=detail))
        gates.append(_gate("V1-V5-REVIEW-VISUAL", "check_review_visual.py",
                           ["--md", md, "--profile", "release_teacher_keypoint",
                            "--json-out", visual], report=visual))
        reports += [detail, visual]
    skipped = []
    kps = [Path(p) for p in args.keypoints] if args.keypoints else keypoints_for(subject)
    kps = [p for p in kps if p.is_file()]
    if kps:
        for kp in kps:
            for md in mds:
                gates.append(_gate("HC20-KEYPOINT-COVERAGE", "check_keypoint_coverage.py",
                                   ["--keypoints", kp, "--md", md], skip_rc=(2,)))
    else:
        skipped.append({"id": "HC20-KEYPOINT-COVERAGE",
                        "reason": f"输入素材/{subject}/ 未发现 *教师重点*.md（SKIPPED 不视为通过）"})
    return {"gates": gates, "artifacts": mds, "reports": reports, "skipped": skipped}


PLAN = {"a2": _a2, "a3": _a3, "a4": _a4, "lv": _lv, "a5": _a5}


def stage_applicable(batch: str, stage: str) -> bool:
    """阶段适用性（机械判定，与 gate_check 同源口径）。"""
    if stage in ("a2", "a3", "a4"):
        return is_question_bearing(batch)
    if stage == "lv":
        return is_question_bearing(batch) and lv_applicable(batch)
    if stage == "a5":
        return is_review_bearing(batch)
    return False


def required_predecessors(batch: str, stage: str):
    if stage == "a2":
        return []
    if stage == "a3":
        return ["a2"]
    if stage == "a4":
        return ["a3"]
    if stage == "lv":
        return ["a4"]
    if stage == "a5":
        # 纯复习资料批次没有 a2/a3/a4，a5 是它的第一个阶段；混合批次仍要求 a4 先行。
        return ["a4"] if is_question_bearing(batch) else []
    return []


# ── 执行 ─────────────────────────────────────────────────────────────────────

def run_command(argv, timeout=900) -> dict:
    try:
        proc = subprocess.run([str(x) for x in argv], cwd=str(BASE), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"argv": [str(x) for x in argv], "rc": proc.returncode,
                "stdout": (proc.stdout or "")[-6000:], "stderr": (proc.stderr or "")[-6000:]}
    except FileNotFoundError as exc:
        return {"argv": [str(x) for x in argv], "rc": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired:
        return {"argv": [str(x) for x in argv], "rc": 124, "stdout": "", "stderr": "timeout"}


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def preflight(batch: str, stage: str, satisfied=()):
    """satisfied：本次运行内已通过（dry-run 也算）的阶段，避免 `--stage all --dry-run` 自己卡自己。"""
    problems = []
    for prev in required_predecessors(batch, stage):
        if prev in satisfied:
            continue
        report = ledger.verify(batch, prev)
        if report["verdict"] == "FAIL":
            problems.append({"stage": prev, "code": report["code"],
                             "detail": next((c["detail"] for c in report["checks"]
                                             if c["status"] == "FAIL"), ""),
                             "fix": f"python {{SKILL}}/scripts/gate_run.py --batch {batch} --stage {prev}"})
    return problems


def execute_stage(batch: str, stage: str, subject: str, args):
    """返回 (plan, results, artifacts, error)；plan 为 None 表示该阶段 NOT_APPLICABLE。"""
    plan = PLAN[stage](batch, subject, args)
    if isinstance(plan, dict) and plan.get("error"):
        return plan, None, [], plan
    gates = plan["gates"]
    artifacts = [Path(p) for p in plan["artifacts"]]
    missing_before = [str(p) for p in artifacts if not p.is_file()]
    if missing_before:
        return plan, None, artifacts, {"error": "ARTIFACT_MISSING",
                                       "hint": "该阶段交付物不存在，先完成对应 Agent 阶段：" + ", ".join(missing_before)}
    results = []
    blocked = None
    for g in gates:
        print(f"  [RUN] {g['id']}: {Path(g['argv'][1]).name} {' '.join(g['argv'][2:])}")
        r = run_command(g["argv"])
        r["id"] = g["id"]
        r["skip_rc"] = sorted(g["skip_rc"])
        if r["rc"] != 0 and r["rc"] not in g["skip_rc"]:
            blocked = {"error": "GATE_BLOCKED", "gate": g["id"], "rc": r["rc"],
                       "hint": (r["stdout"] + r["stderr"]).strip()[-1500:] or "门禁未通过"}
            results.append(r)
            break
        results.append(r)
        if r["rc"] in g["skip_rc"]:
            print(f"  [SKIP] {g['id']}（机械判定不适用，退出码 {r['rc']}，不视为通过）")
    if blocked:
        return plan, results, artifacts, blocked
    missing_after = [str(p) for p in artifacts if not p.is_file()]
    if missing_after:
        return plan, results, artifacts, {"error": "ARTIFACT_MISSING",
                                          "hint": "门禁跑完但交付物不存在：" + ", ".join(missing_after)}
    return plan, results, artifacts, None


def stamp_stage(batch: str, stage: str, results, artifacts, reports, skipped, flags, note=None):
    led, err = ledger.load_ledger(batch)
    if err:
        return None, err
    if led is None:
        led = ledger.new_ledger(batch, tool=TOOL)
    gates = [{"id": r["id"], "argv": r["argv"], "rc": r["rc"],
              "stdout_sha256": sha256_text(r["stdout"]),
              "stderr_sha256": sha256_text(r["stderr"])} for r in results]
    skipped_payload = [dict(s) for s in (skipped or [])]
    for r in results:
        if r["rc"] in (r.get("skip_rc") or []):
            skipped_payload.append({"id": r["id"], "reason": f"退出码 {r['rc']}（机械判定不适用）"})
    stamp = ledger.append_stamp(led, stage, artifacts=artifacts, gate_reports=reports,
                                gates=gates, skipped=skipped_payload, flags=flags,
                                provenance="gate_run", tool=TOOL, note=note)
    try:
        ledger.write_ledger(led)
    except OSError as exc:
        return None, f"STAMP_WRITE_FAILED: {exc}"
    return stamp, None


def main(argv=None) -> int:
    _configure_stdio()
    ap = argparse.ArgumentParser(description="阶段门禁唯一执行入口（gate_run，v2.6.0）")
    ap.add_argument("--batch", "-b", required=True)
    ap.add_argument("--stage", "-s", required=True, choices=[*STAGES, "all"])
    ap.add_argument("--subject", default="", help="科目名（缺省读 workflow_state 的 batch.subject）")
    ap.add_argument("--review", action="append", default=[], help="主复习资料 MD（可多次；缺省按科目自动发现）")
    ap.add_argument("--keypoints", action="append", default=[], help="教师重点原文 MD（可多次；缺省自动发现）")
    ap.add_argument("--golden-absent", action="store_true",
                    help="显式声明无金标准、走 HC-18 降级（写入回执 flags，可审计）")
    ap.add_argument("--dry-run", action="store_true", help="跑门禁但不写回执（产物无法交付）")
    ap.add_argument("--no-stamp", action="store_true", help="同 --dry-run（显式调试口子）")
    ap.add_argument("--json-out", default="", help="把本次执行结论写成 JSON")
    args = ap.parse_args(argv)

    if not ledger.BATCH_RE.match(str(args.batch or "")):
        print(f"[ERROR] 批次号不合规：{args.batch!r}（必须是 batchNNN，如 batch001）", file=sys.stderr)
        return 2

    subject = subject_for(args.batch, args.subject)
    stages = list(STAGES) if args.stage == "all" else [args.stage]
    summary = {"batch": args.batch, "subject": subject, "requested": stages,
               "tool": TOOL, "ts": datetime.now().isoformat(timespec="seconds"),
               "stages": [], "verdict": "PASS", "code": "OK"}
    flags = {"golden_absent": bool(args.golden_absent),
             "dry_run": bool(args.dry_run or args.no_stamp)}

    sync_state_steps(args.batch)
    satisfied = set()
    hint_stage = None

    for stage in stages:
        print(f"\n=== gate_run: {args.batch} / {stage} —— {STAGE_LABEL[stage]} ===")
        if not stage_applicable(args.batch, stage):
            print(f"  [NOT_APPLICABLE] 按产物类型（{', '.join(sorted(product_types(args.batch)))}）该阶段不适用（不写回执）")
            summary["stages"].append({"stage": stage, "verdict": "NOT_APPLICABLE", "code": "NOT_APPLICABLE"})
            continue
        problems = preflight(args.batch, stage, satisfied)
        stage_rec = {"stage": stage, "preflight": problems, "gates": []}
        if problems:
            stage_rec["verdict"], stage_rec["code"] = "BLOCKED", problems[0]["code"]
            summary["stages"].append(stage_rec)
            summary["verdict"], summary["code"] = "BLOCKED", problems[0]["code"]
            print(f"  [BLOCKED] {problems[0]['code']}：前置阶段 {problems[0]['stage']} 没有有效回执")
            print(f"  → 下一步：{problems[0]['fix'].replace('{SKILL}', str(SCRIPTS.parent))}")
            hint_stage = problems[0]["stage"]
            break
        plan, results, artifacts, error = execute_stage(args.batch, stage, subject, args)
        if error:
            stage_rec["verdict"], stage_rec["code"] = "BLOCKED", error.get("error", "BLOCKED")
            stage_rec["detail"] = error
            summary["stages"].append(stage_rec)
            summary["verdict"], summary["code"] = "BLOCKED", error.get("error", "BLOCKED")
            print(f"  [BLOCKED] {error.get('error')}：{error.get('hint', '')}")
            if error.get("error") == "GATE_BLOCKED":
                print(f"  → 若该批次此前已被 HALT：先跑 python {{SKILL}}/scripts/gate_check.py "
                      f"--batch {args.batch} --clear-halt，修复后重跑本阶段")
            hint_stage = stage
            break
        skipped = plan.get("skipped") or []
        reports = [Path(p) for p in (plan.get("reports") or [])]
        stage_rec["gates"] = [{"id": r["id"], "rc": r["rc"]} for r in results]
        if args.dry_run or args.no_stamp:
            stage_rec["verdict"], stage_rec["code"] = "PASS_DRY_RUN", "DRY_RUN"
            summary["stages"].append(stage_rec)
            satisfied.add(stage)
            print("  [DRY-RUN] 门禁通过，但未写回执（产物不可交付）")
            continue
        stamp, err = stamp_stage(args.batch, stage, results, artifacts,
                                 [p for p in reports if p.is_file()], skipped, flags)
        if err or stamp is None:
            stage_rec["verdict"], stage_rec["code"] = "BLOCKED", "STAMP_WRITE_FAILED"
            summary["stages"].append(stage_rec)
            summary["verdict"], summary["code"] = "BLOCKED", "STAMP_WRITE_FAILED"
            print(f"  [BLOCKED] {err or '回执写入失败'}")
            hint_stage = stage
            break
        stage_rec["verdict"] = stamp["verdict"]
        stage_rec["code"] = "STAMP_OK"
        stage_rec["stamp"] = {"seq": stamp["seq"], "hash": stamp.get("hash"),
                              "artifacts": [a["path"] for a in stamp["artifacts"]]}
        summary["stages"].append(stage_rec)
        satisfied.add(stage)
        print(f"  [RECEIPT] seq={stamp['seq']} stage={stage} "
              f"artifacts={[a['path'] for a in stamp['artifacts']]}")
        print(f"  [RECEIPT] {ledger.ledger_path(args.batch)}")

    if summary["verdict"] == "PASS" and summary["stages"] and \
            all(s.get("verdict") == "NOT_APPLICABLE" for s in summary["stages"]):
        summary["verdict"], summary["code"] = "NOT_APPLICABLE", "NOT_APPLICABLE"
    ok = summary["verdict"] in ("PASS", "NOT_APPLICABLE")
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 结论: {summary['verdict']} / {summary['code']} ===")
    if not ok:
        print(f"→ 修复后重跑：python {{SKILL}}/scripts/gate_run.py --batch {args.batch} "
              f"--stage {hint_stage or (stages[0] if stages else 'a2')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
