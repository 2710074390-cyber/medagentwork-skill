#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化一个可独立使用的 MedAgentWork 工作区。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
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

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "example_workspace"

INPUT_README = """# 输入素材

把你自己学校的考试重点、教材摘录、课程安排和获授权的真题资料放入对应科目目录。

## 命名约定

| 文件 | 建议命名 | 说明 |
|---|---|---|
| 教师重点 | `{科目}_教师重点_<学校或日期>.md` | 覆盖门禁按实际文件名读取，脚本不会展开 `*` 通配符 |
| 教材/笔记 | `教材摘录_<章节>.md` | 任意文件名均可 |
| 课程安排 | `课程安排.md` | 可选 |

重点文件不是固定模板：换成另一所学校的重点后，仍使用同一套生成和质量门禁流程。
"""


def _example_relative(relative: Path, subject: str) -> Path:
    """把示例的 输入素材/示例科目/ 映射到目标科目目录。"""
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "输入素材" and parts[1] == "示例科目":
        target_subject = subject or "示例科目"
        name = parts[-1]
        if name == "示例科目_教师重点_示例.md" and target_subject != "示例科目":
            name = f"{target_subject}_教师重点_示例.md"
        return Path("输入素材") / target_subject / name
    return relative


def _copy_example(root: Path, subject: str) -> tuple[int, int]:
    """把内置示例复制到工作区；已存在的文件不覆盖，返回 (新增, 跳过)。"""
    if not EXAMPLE_ROOT.is_dir():
        print(f"[WARN] 未找到内置示例：{EXAMPLE_ROOT}，跳过 --example")
        return 0, 0

    copied = 0
    skipped = 0
    for source in sorted(EXAMPLE_ROOT.rglob("*")):
        if not source.is_file():
            continue
        relative = _example_relative(source.relative_to(EXAMPLE_ROOT), subject)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            skipped += 1
            continue
        shutil.copy2(source, destination)
        copied += 1
        if destination.name == "ALL_questions.json":
            try:
                data = json.loads(destination.read_text(encoding="utf-8"))
                for question in data:
                    if isinstance(question, dict):
                        question["subject"] = subject
                destination.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (OSError, json.JSONDecodeError):
                pass
    return copied, skipped


def _register_example_batch(root: Path, subject: str) -> bool:
    """登记 batch001（仅不存在时创建），返回是否新建。"""
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import workflow_state as ws
    except ImportError as exc:
        print(f"[WARN] 无法导入 workflow_state（{exc}），跳过示例批次登记")
        return False

    state, err = ws.load_state(root)
    if err:
        print(f"[WARN] 无法读取 workflow_state.json（{err}），跳过示例批次登记")
        return False

    batch, created = ws.ensure_batch(state, "batch001")
    if created:
        batch.update(subject=subject or "示例科目", target=3, task_type="example",
                     source="assets/example_workspace")
    if state.get("active_batch") in (None, ""):
        state["active_batch"] = "batch001"
    ws.save_state(state, root)
    return created


def _write_example_guide(root: Path, subject: str) -> bool:
    """写一份示例运行说明；已存在时不覆盖。"""
    guide = root / "示例运行说明.md"
    if guide.exists():
        return False

    subject = subject or "示例科目"
    skill = Path(__file__).resolve().parent.parent.as_posix()
    workspace = root.as_posix()
    guide.write_text(
        f"""# 示例工作区运行说明

本工作区由 `init_workspace.py --example` 创建，包含 3 道示例题，用于先跑通确定性门禁，不需要调用 LLM。

## 0. 自检

```bash
python "{skill}/scripts/doctor.py" --workspace "{workspace}"
```

## 1. 校验示例题库（预期 FAIL=0，WARN 不阻断）

```bash
cd "{workspace}"
python "{skill}/scripts/validate_options.py" --batch batch001 --mode full
```

## 2. 导出 Markdown

```bash
python "{skill}/scripts/qbank.py" export-md --file 中间产物/batch001/ALL_questions.json --out 中间产物/batch001/示例题库.md --title "{subject}·示例题库"
```

## 3. 让 Agent 继续完整五阶段

```text
加载 medagentwork 技能。使用输入素材/{subject}/中的示例教师重点和教材，开始新批次：{subject}，目标 3 题。示例批次 batch001 已登记。
```

## 4. 换成自己的资料

把 `输入素材/{subject}/` 下的文件替换为你自己的资料；教师重点建议命名为：

```text
输入素材/<科目>/<科目>_教师重点_<学校或日期>.md
```

门禁命令按实际文件名读取，脚本不会展开 `*` 通配符。
""",
        encoding="utf-8",
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 MedAgentWork 工作区")
    parser.add_argument("workspace", nargs="?", default=".", help="工作区目录，默认当前目录")
    parser.add_argument("--subject", default="", help="可选科目名，同时创建输入素材子目录")
    parser.add_argument("--example", action="store_true",
                        help="复制内置 3 题示例并登记 batch001，便于立即跑通校验/导出")
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
            json.dumps({"schema_version": 2, "active_batch": None, "halt": {"active": False}},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    readme = root / "输入素材" / "README.md"
    if not readme.exists():
        readme.write_text(INPUT_README, encoding="utf-8")

    print(f"工作区已初始化：{root}")
    if args.subject:
        print(f"科目目录：{root / '输入素材' / args.subject}")

    if args.example:
        target_subject = args.subject or "示例科目"
        copied, skipped = _copy_example(root, target_subject)
        if copied or skipped:
            created = _register_example_batch(root, target_subject)
            print(f"内置示例：新增 {copied} 个文件，跳过 {skipped} 个已存在文件（目标科目：{target_subject}）")
            print(f"示例批次 batch001：{'已登记（3 题）' if created else '已存在，未覆盖'}")
            if _write_example_guide(root, target_subject):
                print(f"示例运行说明：{root / '示例运行说明.md'}")
            else:
                print("示例运行说明已存在，未覆盖")
        else:
            print("示例未复制成功；请检查 skill 包的 assets/example_workspace/ 是否存在。")
    else:
        print("下一步：把本校考试重点和教材放入 输入素材/<科目>/，再运行 doctor.py 检查。")

    doctor = Path(__file__).resolve().parent / "doctor.py"
    print(f'自检命令：python "{doctor.as_posix()}" --workspace "{root.as_posix()}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
