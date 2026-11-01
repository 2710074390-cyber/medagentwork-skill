#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布包 R0-R4 质量门禁编排器。

只调用本发布包实际提供的脚本；不依赖主仓库脚本或固定批次产物。
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


def _configure_stdio() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


BASE = Path.cwd()
SKILL_SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_SCRIPTS.parent
DEFAULT_POLICY = SKILL_SCRIPTS / "quality_policy.json"
DEFAULT_SPEC = SKILL_ROOT / "references/quality-gate.md"
PRODUCT_TYPES = {"question_bank", "prediction_paper", "review_material"}
BUNDLED = {"quality_policy", "schema", "learning_value", "source_concepts", "concept_graph",
           "review_detail", "review_visual", "produce_rules", "keypoint_coverage", "inline_images"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_item(check_id: str, status: str, reason: str, *, required: bool = True,
               details: dict | None = None) -> dict:
    return {"id": check_id, "status": status, "required": required,
            "reason": reason, "details": details or {}}


def run_cmd(cmd: list[str], timeout: int = 300) -> dict:
    resolved = []
    for value in cmd:
        if value.startswith("scripts/"):
            candidate = SKILL_SCRIPTS / Path(value).name
            if not candidate.exists():
                return {"command": " ".join(cmd), "returncode": 125, "stdout": "",
                        "stderr": f"分发包缺少脚本：{candidate.name}"}
            value = str(candidate)
        resolved.append(value)
    try:
        proc = subprocess.run(resolved, cwd=BASE, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        return {"command": " ".join(resolved), "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-2000:], "stderr": (proc.stderr or "")[-2000:]}
    except FileNotFoundError as exc:
        return {"command": " ".join(resolved), "returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired:
        return {"command": " ".join(resolved), "returncode": 124, "stdout": "", "stderr": "timeout"}


def _load_policy(path: Path) -> dict:
    import quality_policy
    return quality_policy.load_policy(path)


def _batch_state(batch: str) -> dict:
    try:
        state = read_json(BASE / "workflow_state.json")
        item = state.get(batch) if isinstance(state, dict) else None
        return item if isinstance(item, dict) else {}
    except Exception:
        return {}


def infer_batch_products(batch: str) -> set[str]:
    state = _batch_state(batch)
    explicit = state.get("product_types")
    if isinstance(explicit, str):
        explicit = [explicit]
    picked = {str(x).strip() for x in (explicit or []) if str(x).strip() in PRODUCT_TYPES}
    if picked:
        return picked
    subject = str(state.get("subject") or "")
    marker = subject + str(state.get("chapter") or "") + str(state.get("exam_type") or "")
    final_dir = BASE / "最终产物" / batch
    names = [p.name for p in final_dir.glob("*")] if final_dir.exists() else []
    types = set()
    if "押题" in marker or any("押题" in n for n in names):
        types.add("prediction_paper")
    if any(p.name.startswith("ALL_questions") and p.suffix == ".json" for p in final_dir.glob("*")):
        types.add("question_bank")
    review_dir = BASE / "复习资料"
    if state.get("steps", {}).get("AGENT5") or (subject and review_dir.exists() and
            list(review_dir.rglob(f"{subject}*主复习资料.md"))):
        types.add("review_material")
    return types or {"question_bank"}


def derive_paths(args) -> None:
    batch = args.batch
    root = BASE / "中间产物" / batch
    final = BASE / "最终产物" / batch
    report = BASE / "reports" / "validate"
    args.questions = args.questions or str(next(iter(sorted(final.glob("ALL_questions_FIXED*.json"))),
                                            final / "ALL_questions_FIXED.json"))
    args.learning_value = args.learning_value or str(report / f"learning_value_{batch}.json")
    args.review = args.review or str(BASE / "复习资料" / f"{args.subject}教师重点版" /
                                      f"{args.subject}教师重点版_主复习资料.md")
    args.keypoints = args.keypoints or str(BASE / "输入素材" / args.subject /
                                            f"{args.subject}_教师重点_锚定清单.md")
    args.kc = args.kc or str(root / "kc_registry.json")
    args.scorecard = args.scorecard or str(report / f"review_scorecard_{batch}.json")


def check_required_inputs(args, profile) -> list[dict]:
    products = infer_batch_products(args.batch)
    required = set(profile.get("required_checks") or [])
    out = [check_item("r0.spec", "PASS" if DEFAULT_SPEC.exists() else "FAIL",
                      f"质量规范：{DEFAULT_SPEC}"),
           check_item("r0.policy", "PASS" if Path(args.policy).exists() else "FAIL",
                      f"质量策略：{args.policy}")]
    if "question_bank" in products or "prediction_paper" in products:
        p = Path(args.questions)
        out.append(check_item("r0.questions", "PASS" if p.exists() else "FAIL",
                              f"当前批次题库：{p}", details={"path": str(p), "sha256": sha256_file(p)}))
    if "review_material" in products:
        p = Path(args.review)
        out.append(check_item("r0.review", "PASS" if p.exists() else "FAIL",
                              f"当前批次复习资料：{p}", details={"path": str(p), "sha256": sha256_file(p)}))
        if "keypoint_coverage" in required:
            p = Path(args.keypoints)
            out.append(check_item("r0.keypoints", "PASS" if p.exists() else "FAIL",
                                  f"教师重点：{p}", details={"path": str(p), "sha256": sha256_file(p)}))
    return out


def _input_detail(path: Path) -> dict:
    return {"path": str(path), "input_sha256": sha256_file(path)}


def check_learning(args, profile, mode):
    path = Path(args.learning_value)
    qpath = Path(args.questions)
    if not qpath.exists():
        return check_item("r2.item_learning_value", "FAIL", f"当前批次题库缺失：{qpath}")
    if not path.exists():
        out = BASE / "reports" / "validate" / f"learning_value_{args.batch}.json"
        r = run_cmd([sys.executable, "scripts/check_learning_value.py", "--file", str(qpath),
                     "--batch", args.batch, "--out", str(out)])
        if r["returncode"] != 0:
            return check_item("r2.item_learning_value", "FAIL", "学习价值子脚本非零退出", details=r)
        path = out
    try:
        data = read_json(path)
    except Exception as exc:
        return check_item("r2.item_learning_value", "FAIL", f"学习价值报告不可读：{exc}", details=_input_detail(qpath))
    expected = sha256_file(qpath)
    if data.get("batch") != args.batch or data.get("input_sha256") != expected:
        return check_item("r2.item_learning_value", "FAIL", "学习价值报告未绑定当前批次/当前输入 hash",
                          details={**_input_detail(qpath), "report": str(path)})
    s = data.get("summary") or {}
    th = profile["thresholds"]
    issues = []
    if int(s.get("fail", 0)) > 0: issues.append(f"FAIL={s['fail']}")
    if float(s.get("per_option_coverage", 0)) < 1 or float(s.get("misconception_coverage", 0)) < 1:
        issues.append("覆盖率不足")
    if float(s.get("source_quote_exact_rate", 0)) < th["source_quote_exact_min"]: issues.append("source exact 不足")
    status = "FAIL" if issues else "PASS"
    if mode == "advisory" and status == "FAIL": status = "WARN"
    return check_item("r2.item_learning_value", status, "; ".join(issues) or "学习价值通过",
                      details={**_input_detail(qpath), "report": str(path), "summary": s})


def check_source_concepts(args):
    qpath = Path(args.questions)
    out = BASE / "reports" / "validate" / f"source_concepts_{args.batch}_{args.stage}.json"
    r = run_cmd([sys.executable, "scripts/check_source_concepts.py", "--file", str(qpath),
                 "--batch", args.batch, "--out", str(out)])
    if r["returncode"] == 0:
        status = "PASS"
    elif r["returncode"] == 2:
        status = "SKIP"
    else:
        status = "FAIL"
    return check_item("r2.source_concepts", status,
                      "概念标注 " + ("通过" if status == "PASS" else "SKIP/失败"),
                      required=status != "SKIP", details={**r, **_input_detail(qpath)})


def check_review(args, profile, mode, kind):
    md = Path(args.review)
    if not md.exists():
        return check_item(f"r2.{kind}", "SKIP", f"复习资料不适用或缺失：{md}", required=False,
                          details=_input_detail(md))
    out = BASE / "reports" / "validate" / f"{kind}_{args.batch}_{args.stage}.json"
    script = "check_review_detail.py" if kind == "review_detail" else "check_review_visual.py"
    cmd = [sys.executable, f"scripts/{script}", "--md", str(md), "--profile", args.profile,
           "--json-out", str(out), "--quiet"]
    if mode == "advisory": cmd.append("--advisory")
    r = run_cmd(cmd)
    if r["returncode"] == 2:
        status = "SKIP"
    elif r["returncode"] != 0 or not out.exists():
        status = "FAIL"
    else:
        try: status = str(read_json(out).get("status") or "FAIL")
        except Exception: status = "FAIL"
    if mode == "advisory" and status == "FAIL": status = "WARN"
    return check_item(f"r2.{kind}", status, f"{kind} {'通过' if status == 'PASS' else status}",
                      required=status != "SKIP", details={**r, **_input_detail(md), "report": str(out)})


def check_keypoints(args):
    kp, md = Path(args.keypoints), Path(args.review)
    if not kp.exists() or not md.exists():
        return check_item("r3.keypoint_coverage", "SKIP", "教师重点或复习资料不在当前批次范围内",
                          required=False, details={**_input_detail(kp), "review": str(md)})
    r = run_cmd([sys.executable, "scripts/check_keypoint_coverage.py", "--keypoints", str(kp), "--md", str(md)])
    return check_item("r3.keypoint_coverage", "PASS" if r["returncode"] == 0 else "FAIL",
                      "教师重点覆盖", details={**r, **_input_detail(kp), "review_sha256": sha256_file(md)})


def bundled_or_skip(cid, label):
    return check_item(cid, "SKIPPED_NOT_BUNDLED", f"{label}：发布包未提供该能力", required=True,
                      details={"availability": "not_bundled"})


def check_produce_rules(args):
    r = run_cmd([sys.executable, "scripts/verify_produce_rules.py"])
    return check_item("r3.produce_rules", "PASS" if r["returncode"] == 0 else "FAIL",
                      "产物形态门禁 " + ("通过" if r["returncode"] == 0 else "失败"), details=r)


def build_checks(args, profile, mode):
    req = set(profile.get("required_checks") or [])
    checks = []
    if args.stage == "r1":
        for name in ("kc.schema.json", "review_detail.schema.json"):
            p = SKILL_ROOT / "schemas" / name
            checks.append(check_item(f"r1.{name[:-5]}", "PASS" if p.exists() else "FAIL", f"Schema {name}"))
        return checks
    if "item_learning_value" in req: checks.append(check_learning(args, profile, mode))
    if "source_concepts" in req: checks.append(check_source_concepts(args))
    checks.append(bundled_or_skip("r2.kc_registry", "KC 注册表"))
    checks.append(bundled_or_skip("r2.scorecard", "评分卡"))
    products = infer_batch_products(args.batch)
    if "review_material" in products:
        if "review_detail" in req: checks.append(check_review(args, profile, mode, "review_detail"))
        if "review_visual" in req: checks.append(check_review(args, profile, mode, "review_visual"))
    elif args.stage in ("r2", "r3"):
        checks.append(check_item("r2.review_detail", "SKIP", "当前批次无复习资料产物", required=False))
        checks.append(check_item("r2.review_visual", "SKIP", "当前批次无复习资料产物", required=False))
    if "concept_graph" in req: checks.append(bundled_or_skip("r2.concept_graph", "KC/概念图"))
    if args.stage == "r3":
        if "produce_rules" in req: checks.append(check_produce_rules(args))
        if "site_freshness" in req: checks.append(bundled_or_skip("r3.site_freshness", "线上新鲜度"))
        if "site_links" in req: checks.append(bundled_or_skip("r3.site_links", "站点链接"))
        if "keypoint_coverage" in req: checks.append(check_keypoints(args))
        if "inline_images" in req: checks.append(bundled_or_skip("r3.inline_images", "线上插图门禁"))
    return checks


def post_release(args):
    return [bundled_or_skip("r4.site_freshness", "线上新鲜度记录"),
            check_item("r4.learning_outcome", "SKIPPED_NOT_BUNDLED", "发布包不提供线上学习结果记录",
                       required=True, details={"availability": "not_bundled"})]


def aggregate(checks, mode):
    blocking = [c["reason"] for c in checks if c.get("required", True) and
                c["status"] in ("FAIL", "SKIPPED_NOT_BUNDLED", "SKIP")]
    warnings = [c["reason"] for c in checks if c["status"] in ("WARN", "SKIP", "SKIPPED_NOT_BUNDLED")]
    if mode == "enforce" and blocking: return "BLOCKED", blocking, warnings
    if blocking or warnings or any(c["status"] == "FAIL" for c in checks): return "WARN", [], warnings
    return "PASS", [], warnings


def render_md(report):
    lines = ["# 全流程质量门禁报告", "", f"> 批次：{report['batch']} ｜ 阶段：{report['stage']} ｜ Profile：{report['profile']} ｜ 模式：{report['mode']}",
             f"> 结论：**{report['status']}** ｜ 时间：{report['generated_at']}", "", "## 检查项", "",
             "| 检查 | 状态 | 必需 | 说明 |", "|---|---|---|---|"]
    lines += [f"| {c['id']} | {c['status']} | {'是' if c.get('required', True) else '否'} | {c['reason']} |" for c in report["checks"]]
    lines += ["", "## 阻断项", ""] + ([f"- {x}" for x in report["blocking"]] or ["无。"])
    lines += ["", "## 警告/跳过", ""] + ([f"- {x}" for x in report["warnings"]] or ["无。"])
    return "\n".join(lines)


def main() -> int:
    _configure_stdio()
    ap = argparse.ArgumentParser(description="发布包 R0-R4 质量门禁")
    ap.add_argument("--stage", required=True, choices=["r0", "r1", "r2", "r3", "r4"])
    ap.add_argument("--batch", required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--mode", choices=["advisory", "enforce"], default="advisory")
    ap.add_argument("--review", default=""); ap.add_argument("--kc", default="")
    ap.add_argument("--questions", default=""); ap.add_argument("--learning-value", default="")
    ap.add_argument("--scorecard", default=""); ap.add_argument("--keypoints", default="")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY)); ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.subject: args.subject = str(_batch_state(args.batch).get("subject") or "")
    args.profile = args.profile or ("release_teacher_keypoint" if args.stage == "r3" else "pilot")
    if args.stage == "r3" and (args.profile != "release_teacher_keypoint" or args.mode != "enforce"):
        print("[FAIL] R3 强制要求 profile=release_teacher_keypoint 且 mode=enforce", file=sys.stderr); return 2
    try: policy = _load_policy(Path(args.policy)); profile = policy["profiles"][args.profile]
    except Exception as exc:
        print(f"[FAIL] 质量策略加载失败：{type(exc).__name__}: {exc}", file=sys.stderr); return 2
    derive_paths(args)
    if args.stage == "r0": checks = check_required_inputs(args, profile)
    elif args.stage == "r4": checks = post_release(args)
    else: checks = build_checks(args, profile, args.mode)
    status, blocking, warnings = aggregate(checks, args.mode)
    now = datetime.now(); out = Path(args.out) if args.out else BASE / "reports/gate" / f"quality_gate_{args.batch}_{args.stage}_{now.strftime('%Y%m%dT%H%M%S')}.json"
    inputs = {}
    for key in ("questions", "review", "keypoints", "learning_value"):
        p = Path(getattr(args, key)); digest = sha256_file(p)
        if digest: inputs[key] = {"path": str(p), "sha256": digest}
    report = {"schema_version": 2, "batch": args.batch, "stage": args.stage, "profile": args.profile,
              "mode": args.mode, "generated_at": now.isoformat(timespec="seconds"), "status": status,
              "checks": checks, "blocking": blocking, "warnings": warnings, "policy_version": policy.get("policy_version"),
              "input_hashes": inputs, "products": sorted(infer_batch_products(args.batch))}
    write_json(out, report); write_text(out.with_suffix(".md"), render_md(report))
    print(f"=== 质量门禁 {args.stage.upper()} / {args.profile} / {args.mode} ===")
    for c in checks: print(f"  [{c['status']}] {c['id']}: {c['reason']}")
    print(f"=== 结论: {status} ===\n  JSON: {out}\n  MD  : {out.with_suffix('.md')}")
    return 0 if status != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
