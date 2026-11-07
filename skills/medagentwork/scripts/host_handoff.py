#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""host_handoff.py — 宿主无关的「阶段交接包」（v2.6.0）

解决的问题：五角色接力原先靠提示词描述「怎么派活」，不同宿主（Claude Code /
Codex / Cursor / WorkBuddy / Trae / DSH / 纯手工）对 subagent 的支持不一样。
本工具把「派活」变成**数据**：一个阶段该读什么、写什么、先验哪条回执、过哪道门禁、
怎么算完成，全部写进 `中间产物/{batch}/_handoff/{stage}.json`。包里**不含任何宿主
工具名**，三种消费方式产出同一份产物字节与门禁回执。

设计纪律：
  - 哈希复用 `gate_ledger.file_sha256`，与回执链同一真相源；
  - 内容完全确定（无时间戳），重复执行产出同一字节；
  - 不改 `gate_run.py`、不写回执、不跑门禁、不新增依赖。

用法（在用户工作区执行，{SKILL}=本 skill 安装目录）：
    python {SKILL}/scripts/host_handoff.py build --batch batchNNN --stage a3
    python {SKILL}/scripts/host_handoff.py brief --batch batchNNN --stage a3
    python {SKILL}/scripts/host_handoff.py brief --batch batchNNN --stage a3 --bundle <path>
退出码：build 0/1；brief 0=完好 / 1=无包 / 2=解析失败 / 3=包已过期
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_ledger as gl  # noqa: E402  文件字节哈希：与回执链同源

try:
    _configure = getattr(sys.stdout, "reconfigure", None)
    if _configure:
        _configure(encoding="utf-8", errors="replace")
except Exception:
    pass

STAGE_META = {
    "a2": {"owner": "MedGen", "role": "references/medgen.md",
           "prompt": "references/prompts/MedGen_current_prompt.md",
           "write_scope": "question_bank", "read": "full"},
    "a3": {"owner": "MedQC", "role": "references/medqc.md",
           "prompt": "references/prompts/MedQC_current_prompt.md",
           "write_scope": "report", "read": "by-id"},
    "a4": {"owner": "MedFix", "role": "references/medfix.md",
           "prompt": "references/prompts/MedFix_current_prompt.md",
           "write_scope": "question_bank", "read": "by-id"},
    "a5": {"owner": "MedReview", "role": "references/medreview.md",
           "prompt": "references/prompts/Agent5_MedReview_Prompt.md",
           "write_scope": "review_material", "read": "by-id"},
}
GATE_CMD = "python {SKILL}/scripts/gate_run.py --batch {batch} --stage {stage}"
# gate_run.py 内建 preflight（消费前验真）；这里给一条可独立执行的回执审计命令，
# 便于宿主在派活前自行确认上游回执链成立。不要编造 gate_run 不存在的 --verify-only。
VERIFY_CMD = "python {SKILL}/scripts/gate_audit.py --batch {batch}"


def _io(batch, stage, root: Path):
    ctx = f"中间产物/{batch}/_ctx.md"
    table = {
        "a2": ([ctx, f"中间产物/{batch}/kaoyan_candidates.json"],
               [f"中间产物/{batch}/ALL_questions.json"]),
        "a3": ([ctx, f"中间产物/{batch}/ALL_questions.json"],
               [f"质检报告/{batch}/A3_质检报告.json"]),
        "a4": ([ctx, f"中间产物/{batch}/ALL_questions.json",
                f"质检报告/{batch}/A3_质检报告.json"],
               [f"最终产物/{batch}/ALL_questions_FIXED.json",
                f"最终产物/{batch}/ALL_questions_FIXED.md",
                f"最终产物/{batch}/AGENT4_追溯日志.json"]),
        "a5": ([ctx], ["复习资料/<科目>/<科目>_主复习资料.md"]),
    }
    ins, outs = table.get(stage, ([], []))
    kept = [p for p in ins if (root / p).is_file() or p.endswith("_ctx.md")]
    return kept, outs


def fingerprint(rows):
    body = json.dumps([r.get("sha256") for r in rows], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def bundle_path(batch, stage, root: Path):
    return root / "中间产物" / batch / "_handoff" / f"{stage}.json"


def build(bundle_batch, stage, root: Path) -> dict:
    meta = STAGE_META.get(stage)
    if not meta:
        raise ValueError(f"{stage} 不是派角色的阶段（lv/final 等纯门禁阶段不生成包）")
    ins, outs = _io(bundle_batch, stage, root)
    inputs = []
    for p in ins:
        f = root / p
        inputs.append({
            "path": p,
            "sha256": gl.file_sha256(f) if f.is_file() else None,
            "exists": f.is_file(),
            "read": meta["read"],
            "selector": "qbank.py subselect" if meta["read"] == "by-id" else None,
        })
    order = ("a2", "a3", "a4", "lv", "a5")
    idx = order.index(stage) if stage in order else -1
    prev = order[idx - 1] if idx > 0 else None
    return {
        "schema_version": "1.0",
        "batch": bundle_batch,
        "stage": stage,
        "owner": meta["owner"],
        "role_skill": meta["role"],
        "prompt_ref": meta["prompt"],
        "ctx": f"中间产物/{bundle_batch}/_ctx.md",
        "inputs": inputs,
        "outputs": [{"path": p, "schema": p.rsplit(".", 1)[-1]} for p in outs],
        "preflight": (VERIFY_CMD.format(SKILL="{SKILL}", batch=bundle_batch)
                      if prev else None),
        "gate": GATE_CMD.format(SKILL="{SKILL}", batch=bundle_batch, stage=stage),
        "done": ([f"{outs[0]} 存在且可解析"] if outs else []) + ["gate 返回 exit 0"],
        "report_format": "三行：结论 / 落点路径 / 阻断原因",
        "write_scope": meta["write_scope"],
        "parallel_safe": meta["write_scope"] != "question_bank",
        "supported_levels": ["L2", "L1", "L0"],
        "inputs_fingerprint": fingerprint(inputs),
        "rebuild_if": "inputs_fingerprint 与当前文件不符 → 丢弃本包，重跑 build",
        "provenance": "medagentwork-skill/host_handoff@v2.6.0",
    }


def is_stale(path: Path, root: Path):
    if not path.is_file():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    rows = []
    for i in d.get("inputs", []):
        f = root / i["path"]
        rows.append({"sha256": gl.file_sha256(f) if f.is_file() else None})
    return fingerprint(rows) != d.get("inputs_fingerprint")


def cmd_build(args, root: Path) -> int:
    try:
        b = build(args.batch, args.stage, root)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    p = bundle_path(args.batch, args.stage, root)
    text = json.dumps(b, ensure_ascii=False, indent=2, sort_keys=True)
    if p.is_file() and p.read_text(encoding="utf-8") == text:
        print(f"unchanged: {p}")
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print(f"written: {p}")
    return 0


def cmd_brief(args, root: Path) -> int:
    p = Path(args.bundle) if args.bundle else bundle_path(args.batch, args.stage, root)
    stale = is_stale(p, root)
    if stale is None:
        print(f"[!] 没有 {p}；先跑：python {{SKILL}}/scripts/host_handoff.py build "
              f"--batch {args.batch} --stage {args.stage}")
        return 1
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"[!] 交接包无法解析：{p}")
        return 2
    print(f"══ 批次 {d['batch']} ｜ 阶段 {d['stage']} ｜ 执行者 {d['owner']}（宿主无关交接单）")
    print(f"规则正文：{d['role_skill']}　提示词：{d['prompt_ref']}")
    print(f"起步上下文：{d['ctx']}（L1 单会话每阶段重读一次）")
    print("读：")
    for i in d["inputs"]:
        print(f"  - [{i['read']}] {i['path']}  sha256={str(i['sha256'])[:12]}  "
              f"{'OK' if i['exists'] else '缺失'}")
    print("写：")
    for o in d["outputs"]:
        print(f"  - {o['path']}")
    if d.get("preflight"):
        print(f"先验回执：{d['preflight']}")
    print(f"阶段门禁：{d['gate']}")
    print("完成判据：" + "；".join(d["done"]))
    print(f"回报格式：{d['report_format']}")
    print(f"写范围：{d['write_scope']} ｜ 可并行：{d['parallel_safe']} ｜ 支持宿主档：{','.join(d['supported_levels'])}")
    if stale:
        print("[!] 包已过期（产物 sha 变了）：重跑 build 后再使用")
        return 3
    print("[OK] 包完好")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="宿主无关的阶段交接包（v2.6.0）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "brief"):
        p = sub.add_parser(name, help="生成交接包" if name == "build" else "打印人读交接单")
        p.add_argument("--batch", "-b", required=True)
        p.add_argument("--stage", "-s", required=True, choices=list(STAGE_META))
        if name == "brief":
            p.add_argument("--bundle", default=None, help="交接包路径覆盖（测试用）")
    args = ap.parse_args(argv)
    root = Path.cwd()
    return cmd_build(args, root) if args.cmd == "build" else cmd_brief(args, root)


if __name__ == "__main__":
    sys.exit(main())
