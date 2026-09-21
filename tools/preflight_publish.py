# -*- coding: utf-8 -*-
"""preflight_publish.py — 投稿/发布前预检

按主流 Agent Skills 分发渠道的收录规范，对本仓库的 skill 包做一次静态自检，
把「能不能投、还差什么」变成可执行的检查项，而不是靠人工比对文档。

覆盖的规范来源：
  - Agent Skills 标准（agentskills.io）：SKILL.md 必需 + name/description 最少字段
  - Claude 自定义 skill 上传校验：description ≤ 1024 字符；name 不得含保留字
    "claude" / "anthropic"
  - agentic-awesome-skills（AAS）社区库 validate_skills.py：
      frontmatter 必需 name / description / category / risk / source / date_added
      description ≤ 300 字符（建议 ≤200）
      name 必须与目录名一致
      正文需含可匹配 `## When to Use ...` 的章节
      正文相对链接不得悬空
      tags ≤ 5 个；risk ∈ {none,safe,critical,offensive,unknown}

用法：
    python tools/preflight_publish.py                # 检查仓库内所有 skill
    python tools/preflight_publish.py --strict       # 警告也视为失败（对应 AAS --strict）
    python tools/preflight_publish.py --skill medagentwork
退出码：0 = 通过（或仅警告）；1 = 存在致命项；2 = 用法/路径错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

RESERVED_NAME_WORDS = ("claude", "anthropic")
DESC_UPLOAD_MAX = 1024          # Claude 自定义 skill 上传校验上限
DESC_HARD_MAX = 300             # AAS validate_skills.py 硬限
DESC_RECOMMENDED = 200          # AAS 模板建议值
VALID_RISK = {"none", "safe", "critical", "offensive", "unknown"}
VALID_SOURCE = {"community", "official", "self"}
AAS_REQUIRED = ["name", "description", "category", "risk", "source", "date_added"]
WHEN_TO_USE_RE = re.compile(
    r"^##\s+(When to Use|Use this skill when|When to activate this skill)", re.M | re.I
)
REL_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

FATAL, WARN, INFO = [], [], []


def _rec(level: str, skill: str, msg: str) -> None:
    {"FATAL": FATAL, "WARN": WARN, "INFO": INFO}[level].append((skill, msg))


def parse_frontmatter(text: str):
    """返回 (frontmatter dict, 正文)。仅支持顶层标量键（够用且无 YAML 依赖）。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text
    fm = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith(" ") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, "\n".join(lines[end + 1:])


def check_skill(skill_dir: Path) -> None:
    name_dir = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        _rec("FATAL", name_dir, "缺少 SKILL.md")
        return

    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        _rec("FATAL", name_dir, "SKILL.md 缺少合法的 YAML frontmatter（首行需为 ---）")
        return

    # ── name ──
    name = fm.get("name", "")
    if not name:
        _rec("FATAL", name_dir, "frontmatter 缺少 name")
    else:
        if name != name_dir:
            _rec("FATAL", name_dir, f"name='{name}' 与目录名 '{name_dir}' 不一致")
        if not re.fullmatch(r"[a-z0-9\-]+", name):
            _rec("WARN", name_dir, f"name='{name}' 建议仅用小写字母/数字/连字符")
        hit = [w for w in RESERVED_NAME_WORDS if w in name]
        if hit:
            _rec("FATAL", name_dir, f"name 含保留字 {hit}（Claude 上传校验会拒绝）")

    # ── description ──
    desc = fm.get("description", "")
    if not desc:
        _rec("FATAL", name_dir, "frontmatter 缺少 description")
    else:
        n = len(desc)
        if n > DESC_UPLOAD_MAX:
            _rec("FATAL", name_dir, f"description {n} 字符 > Claude 上传上限 {DESC_UPLOAD_MAX}")
        elif n > DESC_HARD_MAX:
            _rec("WARN", name_dir, f"description {n} 字符 > AAS 硬限 {DESC_HARD_MAX}")
        elif n > DESC_RECOMMENDED:
            _rec("INFO", name_dir, f"description {n} 字符 > AAS 建议值 {DESC_RECOMMENDED}")

    # ── AAS 必需字段 ──
    for f in AAS_REQUIRED:
        if not fm.get(f):
            _rec("WARN", name_dir, f"缺少 AAS 必需字段 `{f}`（收录到社区库前需补）")

    risk = fm.get("risk")
    if risk and risk not in VALID_RISK:
        _rec("FATAL", name_dir, f"risk='{risk}' 非法，应为 {sorted(VALID_RISK)}")
    src = fm.get("source")
    if src and src not in VALID_SOURCE:
        _rec("FATAL", name_dir, f"source='{src}' 非法，应为 {sorted(VALID_SOURCE)}")

    date_added = fm.get("date_added")
    if date_added and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_added):
        _rec("FATAL", name_dir, f"date_added='{date_added}' 需为 YYYY-MM-DD")

    tags = fm.get("tags")
    if tags and tags.count(",") + 1 > 5:
        _rec("WARN", name_dir, f"tags 超过 5 个（当前 {tags.count(',') + 1}）")

    # ── 必需章节 ──
    if not WHEN_TO_USE_RE.search(body):
        _rec("WARN", name_dir, "正文缺少可匹配 `## When to Use ...` 的章节（AAS 严格模式硬失败）")

    # ── 悬空链接（相对路径必须真实存在）──
    for _, href in REL_LINK_RE.findall(body):
        if href.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = href.split("#")[0]
        if target and not (skill_dir / target).exists():
            _rec("FATAL", name_dir, f"悬空链接: {href}")

    # ── 正文反引号中的 scripts/ 路径 ──
    for p in sorted(set(re.findall(r"`(scripts/[\w./\-]+)`", body))):
        if not (skill_dir / p).exists():
            _rec("FATAL", name_dir, f"引用了不存在的文件: {p}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent Skill 投稿/发布前预检")
    ap.add_argument("--skill", default="", help="只检查指定 skill（目录名）")
    ap.add_argument("--strict", action="store_true", help="警告也视为失败")
    args = ap.parse_args()

    if not SKILLS_DIR.is_dir():
        print(f"✗ 找不到 skills/ 目录: {SKILLS_DIR}")
        return 2

    targets = (
        [SKILLS_DIR / args.skill]
        if args.skill
        else sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    )
    if args.skill and not targets[0].is_dir():
        print(f"✗ 找不到 skill: {targets[0]}")
        return 2

    for d in targets:
        check_skill(d)

    print(f"═══ Skill 投稿预检（{len(targets)} 个 skill）═══\n")
    for level, label in ((FATAL, "❌ 致命"), (WARN, "⚠️  警告"), (INFO, "ℹ️  建议")):
        if not level:
            continue
        print(f"{label}（{len(level)}）")
        for skill, msg in level:
            print(f"  [{skill}] {msg}")
        print()

    failed = bool(FATAL) or (args.strict and bool(WARN))
    print("─" * 46)
    print(f"结论: {'✗ 未通过' if failed else '✓ 通过'}"
          f"  致命={len(FATAL)} 警告={len(WARN)} 建议={len(INFO)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
