#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化一个可独立使用的 MedAgentWork 工作区。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DIRECTORIES = (
    "输入素材",
    "中间产物",
    "质检报告",
    "最终产物",
    "复习资料",
    "GoldenSet/structured",
    "reports/validate",
    "reports/gate",
    "archive",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 MedAgentWork 工作区")
    parser.add_argument("workspace", nargs="?", default=".", help="工作区目录，默认当前目录")
    parser.add_argument("--subject", default="", help="可选科目名，同时创建输入素材子目录")
    args = parser.parse_args()

    root = Path(args.workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for relative in DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)
    if args.subject:
        (root / "输入素材" / args.subject).mkdir(parents=True, exist_ok=True)

    state = root / "workflow_state.json"
    if not state.exists():
        state.write_text(
            json.dumps({"schema_version": 2, "active_batch": None, "halt": {"active": False}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    readme = root / "输入素材" / "README.md"
    if not readme.exists():
        readme.write_text(
            "# 输入素材\n\n把你自己学校的考试重点、教材摘录、课程安排和获授权的真题资料放入对应科目目录。\n\n重点文件不是固定模板：换成另一所学校的重点后，仍使用同一套生成和质量门禁流程。\n",
            encoding="utf-8",
        )

    print(f"工作区已初始化：{root}")
    print("下一步：把本校考试重点和教材放入 输入素材/{科目}/，再让 Agent 开始新批次。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
