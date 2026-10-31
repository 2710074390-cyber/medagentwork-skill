#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_review_visual.py — 复习资料视觉/排版门禁（V1–V5 + V14）

规范单一事实来源：references/review-visual-spec.md
检查对象：复习资料 MD（BPA 教师重点版 / 教学计划版 / 课程安排版）

自动可判定项：
  V1 三色覆盖：#### 卡片标题中带 🔴🟡🟢 的比例
  V2 Callout：每模块数量与类型数
  V3 视觉呼吸：连续纯文本行数
  V4 展开区：每模块 #### 🔬 展开 数量；禁用 <details>/<summary>
  V5 表格：每模块表格块数量
  V14 导出兼容：禁用 Mermaid、禁用 ** 强调、<b>/<i> 必须配对

退出码：0 = PASS/WARN；1 = FAIL；2 = SKIP（文件缺失/无内容）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_POLICY = SCRIPT_DIR / "quality_policy.json"
DEFAULT_PROFILE = "release_teacher_keypoint"

DEFAULTS = {
    "visual_tier_coverage_min": 0.90,
    "visual_callout_density_min": 4.0,
    "visual_callout_types_min": 4,
    "visual_expand_density_min": 2.0,
    "visual_tables_per_module_min": 2,
    "visual_plain_text_run_max": 10,
}

CONTENT_HEADING_RE = re.compile(
    r"^##\s+(模块|第[0-9一二三四五六七八九十百]+(?:周|讲|次|课时|章)|Week\s*\d+|Lecture\s*\d+)",
    re.I,
)
APPENDIX_HEADING_RE = re.compile(
    r"^##\s+(附[录件]|索引|术语|口诀|数字锚|答案|自测答案|使用指南|图例|"
    r"科目蓝图|阅读路径|记忆主轴|高频陷阱|疾病谱系|概念地图)",
    re.I,
)
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]")

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


def _configure_stdio() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load_thresholds(profile: str, policy_path: Path) -> dict:
    """读取 quality_policy.json 的 visual_* 阈值；缺失回退默认值。"""
    out = dict(DEFAULTS)
    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        th = (data.get("profiles", {}).get(profile, {}) or {}).get("thresholds", {}) or {}
        for key in DEFAULTS:
            if key in th:
                out[key] = th[key]
        # 兼容旧键名
        out["visual_callout_density_min"] = th.get(
            "callout_density_min", out["visual_callout_density_min"])
        out["visual_expand_density_min"] = th.get(
            "expand_density_min", out["visual_expand_density_min"])
    except Exception:
        pass
    return out


def split_sections(lines: list[str]) -> list[dict]:
    """按模块/周讲标题切分；没有匹配标题时整篇视为一个内容段。"""
    sections: list[dict] = []
    title = "全文"
    body: list[str] = []
    is_content = False
    in_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        if not in_fence and stripped.startswith("## "):
            if body:
                sections.append({"title": title, "lines": body, "content": is_content})
            title = stripped[3:].strip()
            is_content = bool(CONTENT_HEADING_RE.match(stripped))
            body = []
            continue
        body.append(line)

    if body:
        sections.append({"title": title, "lines": body, "content": is_content})

    content = [s for s in sections if s["content"]]
    if not content:
        return [{"title": "全文", "lines": lines, "content": True}]
    return content


def analyze_section(title: str, lines: list[str]) -> dict:
    data = {
        "title": title,
        "cards": 0,
        "tiered_cards": 0,
        "callouts": 0,
        "callout_types": set(),
        "expand": 0,
        "tables": 0,
        "max_plain_run": 0,
    }
    in_fence = False
    plain_run = 0
    table_run = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            plain_run = 0
            table_run = 0
            continue
        if in_fence:
            continue

        if stripped.startswith("#### "):
            heading = stripped[5:].strip()
            if heading.startswith("🔬"):
                data["expand"] += 1
            elif not heading.startswith(("🏥", "📌", "🔄")):
                data["cards"] += 1
                if heading.startswith(("🔴", "🟡", "🟢")) or re.search(
                        r"【(掌握|熟悉|了解)级】", heading):
                    data["tiered_cards"] += 1
            plain_run = 0
            table_run = 0
            continue

        if stripped.startswith("|"):
            table_run += 1
            if table_run == 1:
                data["tables"] += 1
            plain_run = 0
            continue
        table_run = 0

        match = CALLOUT_RE.match(stripped)
        if match:
            data["callouts"] += 1
            data["callout_types"].add(match.group(1).lower())
            plain_run = 0
            continue

        if not stripped or stripped.startswith(
                ("#", "---", "<b>", "<i>", "📌", "🔄", "- ", "1. ", "* ", "![")):
            plain_run = 0
            continue

        plain_run += 1
        data["max_plain_run"] = max(data["max_plain_run"], plain_run)

    data["callout_types"] = len(data["callout_types"])
    return data


def global_scan(lines: list[str]) -> dict:
    result = {
        "details": 0,
        "mermaid": False,
        "double_star": 0,
        "b_open": 0,
        "b_close": 0,
        "i_open": 0,
        "i_close": 0,
    }
    in_fence = False
    for line in lines:
        raw = line.strip()
        if raw.startswith("```"):
            if not in_fence and raw.lower().startswith("```mermaid"):
                result["mermaid"] = True
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # V14 豁免行内代码中的教学示例
        stripped = re.sub(r"`[^`]*`", "", raw)
        lower = stripped.lower()
        if "<details" in lower or "</details" in lower or "<summary" in lower:
            result["details"] += 1
        result["double_star"] += stripped.count("**")
        result["b_open"] += stripped.count("<b>")
        result["b_close"] += stripped.count("</b>")
        result["i_open"] += stripped.count("<i>")
        result["i_close"] += stripped.count("</i>")
    return result


def check(rule: str, status: str, detail: str, counts: dict | None = None) -> dict:
    return {"id": rule, "status": status, "detail": detail, "counts": counts or {}}


def build_report(md_path: Path, profile: str, mode: str, thresholds: dict,
                 advisory: bool) -> dict:
    if not md_path.exists():
        return {
            "status": SKIP,
            "file": str(md_path),
            "profile": profile,
            "mode": mode,
            "thresholds": thresholds,
            "summary": {},
            "checks": [check("FILE", SKIP, f"复习资料不存在：{md_path}")],
            "blocking": [],
            "warnings": [f"复习资料不存在：{md_path}"],
        }

    text = md_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    sections = [analyze_section(s["title"], s["lines"]) for s in split_sections(lines)]
    scan = global_scan(lines)

    checks: list[dict] = []

    # V1 三色覆盖
    total_cards = sum(s["cards"] for s in sections)
    tiered_cards = sum(s["tiered_cards"] for s in sections)
    if total_cards == 0:
        checks.append(check("V1", SKIP, "未检测到 #### 卡片标题；教学计划版按文字等级人工抽检", {
            "cards": 0, "tiered_cards": 0}))
    else:
        ratio = tiered_cards / total_cards
        status = PASS if ratio >= thresholds["visual_tier_coverage_min"] else FAIL
        checks.append(check("V1", status,
                            f"三色覆盖 {ratio:.1%}（{tiered_cards}/{total_cards}），"
                            f"要求 ≥{thresholds['visual_tier_coverage_min']:.0%}",
                            {"cards": total_cards, "tiered_cards": tiered_cards,
                             "ratio": round(ratio, 4)}))

    # V2 Callout
    min_callouts = thresholds["visual_callout_density_min"]
    min_types = int(thresholds["visual_callout_types_min"])
    v2_ok = True
    for section in sections:
        if section["callouts"] < min_callouts:
            v2_ok = False
            checks.append(check("V2", FAIL,
                                f"{section['title']}：Callout {section['callouts']} < {min_callouts:g}",
                                {"title": section["title"], "callouts": section["callouts"]}))
        elif section["callout_types"] < min_types:
            v2_ok = False
            checks.append(check("V2", WARN,
                                f"{section['title']}：Callout 类型 {section['callout_types']} < {min_types}",
                                {"title": section["title"], "callout_types": section["callout_types"]}))
    if v2_ok:
        checks.append(check("V2", PASS, f"Callout 密度达标（{len(sections)} 个内容段）"))

    # V3 视觉呼吸
    max_run = max((s["max_plain_run"] for s in sections), default=0)
    max_allowed = int(thresholds["visual_plain_text_run_max"])
    checks.append(check(
        "V3", PASS if max_run <= max_allowed else FAIL,
        f"最长连续纯文本 {max_run} 行，上限 {max_allowed}",
        {"max_plain_text_run": max_run, "limit": max_allowed}))

    # V4 展开区 + details
    min_expand = thresholds["visual_expand_density_min"]
    for section in sections:
        if section["expand"] < min_expand:
            checks.append(check("V4", FAIL,
                                f"{section['title']}：展开区 {section['expand']} < {min_expand:g}",
                                {"title": section["title"], "expand": section["expand"]}))
    if scan["details"]:
        checks.append(check("V4", FAIL, f"出现 <details>/<summary> {scan['details']} 处；"
                                        "请改为 #### 🔬 展开：",
                            {"details": scan["details"]}))
    elif all(s["expand"] >= min_expand for s in sections):
        checks.append(check("V4", PASS, f"展开区密度达标（{len(sections)} 个内容段）"))

    # V5 表格
    min_tables = thresholds["visual_tables_per_module_min"]
    v5_ok = True
    for section in sections:
        if section["tables"] < min_tables:
            v5_ok = False
            checks.append(check("V5", WARN,
                                f"{section['title']}：表格块 {section['tables']} < {min_tables}",
                                {"title": section["title"], "tables": section["tables"]}))
    if v5_ok:
        checks.append(check("V5", PASS, f"表格密度达标（{len(sections)} 个内容段）"))

    # V14 导出兼容
    v14_issues = []
    if scan["mermaid"]:
        v14_issues.append("出现 ```mermaid（改为 ASCII 图）")
    if scan["double_star"]:
        v14_issues.append(f"`**` 强调 {scan['double_star']} 处（改用 <b>）")
    if scan["details"]:
        v14_issues.append("出现 <details>/<summary>")
    if scan["b_open"] != scan["b_close"]:
        v14_issues.append(f"<b> 配对不一致（{scan['b_open']}/{scan['b_close']}）")
    if scan["i_open"] != scan["i_close"]:
        v14_issues.append(f"<i> 配对不一致（{scan['i_open']}/{scan['i_close']}）")
    checks.append(check("V14", FAIL if v14_issues else PASS,
                        "; ".join(v14_issues) if v14_issues else "导出兼容检查通过",
                        scan))

    blocking = [c["detail"] for c in checks if c["status"] == FAIL]
    warnings = [c["detail"] for c in checks if c["status"] == WARN]

    if advisory and blocking:
        warnings.extend(f"[advisory] {item}" for item in blocking)
        blocking = []
        for item in checks:
            if item["status"] == FAIL:
                item["status"] = WARN
                item["detail"] = "[advisory] " + item["detail"]

    if blocking:
        status = FAIL
    elif warnings:
        status = WARN
    else:
        status = PASS

    summary = {
        "sections": len(sections),
        "cards": total_cards,
        "tiered_cards": tiered_cards,
        "tier_coverage": round(tiered_cards / total_cards, 4) if total_cards else None,
        "callouts": sum(s["callouts"] for s in sections),
        "expand_blocks": sum(s["expand"] for s in sections),
        "tables": sum(s["tables"] for s in sections),
        "max_plain_text_run": max_run,
        "details": scan["details"],
        "mermaid": scan["mermaid"],
        "double_star": scan["double_star"],
    }
    return {
        "status": status,
        "file": str(md_path),
        "profile": profile,
        "mode": mode,
        "thresholds": thresholds,
        "summary": summary,
        "checks": checks,
        "blocking": blocking,
        "warnings": warnings,
    }


def render_md(report: dict) -> str:
    lines = [
        "# 复习资料视觉门禁报告",
        "",
        f"> 文件：`{report['file']}`",
        f"> Profile：{report['profile']} ｜ 模式：{report['mode']} ｜ 结论：**{report['status']}**",
        "",
        "| 规则 | 状态 | 说明 |",
        "|---|---|---|",
    ]
    for item in report.get("checks", []):
        detail = str(item.get("detail", "")).replace("|", "\\|")
        lines.append(f"| {item['id']} | {item['status']} | {detail} |")
    summary = report.get("summary", {})
    if summary:
        lines += [
            "",
            "## 汇总",
            "",
            f"- 内容段：{summary.get('sections')}",
            f"- 卡片：{summary.get('cards')}；三色覆盖：{summary.get('tier_coverage')}",
            f"- Callout：{summary.get('callouts')}；展开区：{summary.get('expand_blocks')}；"
            f"表格块：{summary.get('tables')}",
            f"- 最长连续纯文本：{summary.get('max_plain_text_run')} 行",
        ]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict, json_out: str, md_out: str) -> None:
    if json_out:
        path = Path(json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    if md_out:
        path = Path(md_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_md(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="复习资料视觉/排版门禁（V1–V5 + V14）")
    parser.add_argument("--md", required=True, help="复习资料 Markdown")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--mode", default="auto",
                        choices=["auto", "teacher_keypoint", "teaching_plan",
                                 "course_schedule", "module"])
    parser.add_argument("--json-out", default="")
    parser.add_argument("--md-out", default="")
    parser.add_argument("--advisory", action="store_true",
                        help="FAIL 降级为 WARN（试点/非正式发布）")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    _configure_stdio()
    thresholds = load_thresholds(args.profile, Path(args.policy))
    report = build_report(Path(args.md), args.profile, args.mode, thresholds, args.advisory)
    write_outputs(report, args.json_out, args.md_out)

    if not args.quiet:
        print(f"=== 复习资料视觉门禁 {args.md} ===")
        for item in report.get("checks", []):
            print(f"  [{item['status']}] {item['id']}  {item['detail']}")
        print(f"\n结论: {report['status']}"
              f"  错误={len(report.get('blocking', []))}"
              f"  警告={len(report.get('warnings', []))}")

    if report["status"] == SKIP:
        return 2
    if report["status"] == FAIL:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
