#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py — MedAgentWork 首次使用 / 环境自检

在用户工作区运行，检查：
  - Python 版本（>= 3.10）
  - skill 目录是否完整（SKILL.md / pipeline.yaml / 核心脚本 / 示例数据）
  - 工作区目录、workflow_state.json
  - 输入素材（科目目录、教师重点文件命名）
  - GoldenSet（有/无，决定是否走 --golden-absent 降级）
  - 可选依赖（PyYAML / jsonschema / jieba；缺失不影响核心管线）

用法：
    python {SKILL}/scripts/doctor.py --workspace ./我的医学复习
    python {SKILL}/scripts/doctor.py            # 默认检查当前目录

退出码：0 = 无 ERROR；1 = 存在 ERROR（先修复再开始批次）
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

REQUIRED_DIRS = (
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
MATERIAL_SUFFIXES = (".md", ".txt", ".doc", ".docx")
OPTIONAL_DEPS = (
    ("yaml", "PyYAML"),
    ("jsonschema", "jsonschema"),
    ("jieba", "jieba"),
)

errors: list[str] = []
warnings: list[str] = []
infos: list[str] = []


def ok(message: str) -> None:
    print(f"[OK]    {message}")


def warn(message: str) -> None:
    warnings.append(message)
    print(f"[WARN]  {message}")


def error(message: str) -> None:
    errors.append(message)
    print(f"[ERROR] {message}")


def info(message: str) -> None:
    infos.append(message)
    print(f"[INFO]  {message}")


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _load_thresholds() -> dict:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import pipeline_config as pc

    return pc.load_thresholds(force_reload=True)


def _load_policy() -> dict:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import quality_policy as qp

    return qp.load_policy()


def _load_state(workspace: Path):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import workflow_state as ws

    state, err = ws.load_state(workspace)
    if err:
        return None, err, ws
    return state, None, ws


def check_skill() -> None:
    print("\n== skill 完整性 ==")
    required = {
        "SKILL.md": SKILL_ROOT / "SKILL.md",
        "pipeline.yaml": SKILL_ROOT / "pipeline.yaml",
        "quality_policy.json": SCRIPTS_DIR / "quality_policy.json",
        "validate_options.py": SCRIPTS_DIR / "validate_options.py",
        "assets/example_workspace": SKILL_ROOT / "assets" / "example_workspace",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        error(f"skill 目录缺少文件：{', '.join(missing)}（安装不完整，请重新获取完整 skill 目录）")
    else:
        ok(f"skill 目录完整：{SKILL_ROOT}")

    try:
        thresholds = _load_thresholds()
        ok(f"pipeline.yaml 可解析，读取到 {len(thresholds)} 个阈值")
    except Exception as exc:
        error(f"pipeline.yaml / pipeline_config.py 读取失败：{type(exc).__name__}: {exc}")

    try:
        policy = _load_policy()
        ok(f"quality_policy.json 可解析，包含 {len(policy.get('profiles', {}))} 个 profile")
    except Exception as exc:
        error(f"quality_policy.json 校验失败：{type(exc).__name__}: {exc}")


def check_workspace(workspace: Path) -> None:
    print("\n== 工作区 ==")
    if not workspace.exists():
        error(f"工作区不存在：{workspace}；先运行 init_workspace.py 创建")
        return
    ok(f"工作区：{workspace}")

    if (workspace / "SKILL.md").exists() and (workspace / "scripts").is_dir():
        error("当前目录看起来是 skill 安装目录；请在单独的用户工作区运行，或显式传入 --workspace")
        return

    missing_dirs = [d for d in REQUIRED_DIRS if not (workspace / d).is_dir()]
    if missing_dirs:
        warn(f"缺少 {len(missing_dirs)} 个目录：{', '.join(missing_dirs)}；可运行 init_workspace.py 补齐")
    else:
        ok(f"工作区结构完整（{len(REQUIRED_DIRS)}/{len(REQUIRED_DIRS)} 个目录）")

    state, err, ws = _load_state(workspace)
    if err:
        error(f"workflow_state.json 不可用：{err}；先运行 init_workspace.py")
        return
    issues = ws.validate_state(state)
    if issues:
        error(f"workflow_state.json 结构问题：{issues[0]}（共 {len(issues)} 项）")
    else:
        batches = [k for k in state if isinstance(state[k], dict) and str(k).startswith("batch")]
        ok(f"workflow_state.json 结构通过，已登记 {len(batches)} 个批次")


def check_materials(workspace: Path) -> str:
    print("\n== 输入素材 ==")
    root = workspace / "输入素材"
    if not root.is_dir():
        return ""

    subjects = [p for p in root.iterdir() if p.is_dir()]
    if not subjects:
        warn("输入素材 下还没有科目目录；可用 --subject <科目> 或 --example 创建")
        return ""

    selected_subject = ""
    for subject in sorted(subjects, key=lambda p: p.name):
        files = [
            f
            for f in subject.iterdir()
            if f.is_file() and f.suffix.lower() in MATERIAL_SUFFIXES and f.name != "README.md"
        ]
        if not files:
            warn(f"输入素材/{subject.name}/ 为空；请放入教材、笔记或教师重点")
            continue

        keypoints = [f for f in files if "重点" in f.name]
        expected_prefix = f"{subject.name}_教师重点_"
        mismatched = [f.name for f in keypoints if not f.name.startswith(expected_prefix)]
        detail = f"输入素材/{subject.name}/：{len(files)} 个文件"
        if keypoints:
            detail += f"，其中教师重点 {len(keypoints)} 个"
        ok(detail)

        if not keypoints:
            info(f"输入素材/{subject.name}/ 未发现教师重点文件；复习资料覆盖门禁将 SKIPPED（不等于通过）")
        else:
            for name in mismatched:
                warn(
                    f"教师重点文件名建议为 {expected_prefix}<学校或日期>.md；当前为 {name}。"
                    "门禁命令按实际文件名读取，脚本不会展开 * 通配符"
                )

        if not selected_subject:
            selected_subject = subject.name

    if not selected_subject:
        warn("没有可用的输入素材；先放入资料或使用内置示例")
    return selected_subject


def check_golden_set(workspace: Path) -> int:
    print("\n== 金标准（GoldenSet） ==")
    gs_root = workspace / "GoldenSet"
    files = []
    if gs_root.is_dir():
        files = sorted(gs_root.rglob("*.json"))
    if files:
        ok(f"发现 {len(files)} 个金标准文件")
    else:
        warn("未发现金标准文件；最终配额检查必须显式加 --golden-absent（该批次无金标准兜底）")
    return len(files)


def check_optional_deps() -> None:
    print("\n== 可选依赖 ==")
    for module, label in OPTIONAL_DEPS:
        state = "已安装" if _has_module(module) else "未安装（不影响核心管线）"
        info(f"{label}: {state}")


def print_next_steps(workspace: Path, subject: str, golden_count: int) -> None:
    print("\n== 下一步 ==")
    skill_scripts = SCRIPTS_DIR.as_posix()
    if not subject:
        print("  1) 先创建可运行示例（3 道题，直接跑校验/导出）：")
        print(f'     python "{skill_scripts}/init_workspace.py" "{workspace}" --subject <科目> --example')
        print("  2) 再用自己的资料替换 输入素材/ 下的示例文件")
    else:
        print("  1) 把下面这句发给 Agent，开始一个新批次：")
        print(
            f"     加载 medagentwork 技能。使用输入素材/{subject}/ 中的教师重点和教材，"
            f"开始新批次：{subject}，目标 <N> 题。"
        )
    if golden_count == 0:
        print("  2) 没有金标准时，最终配额检查使用：")
        print(
            f'     python "{skill_scripts}/kaoyan_picker.py" check '
            f'--file 最终产物/<batchID>/ALL_questions_FIXED.json --golden-absent'
        )
    print(f"  3) 完整首次使用流程见 {SKILL_ROOT.as_posix()}/SKILL.md 的「首次使用：Agent 必须执行的 5 步」")


def main() -> int:
    parser = argparse.ArgumentParser(description="MedAgentWork 首次使用/环境自检")
    parser.add_argument("--workspace", default=".", help="用户工作区目录，默认当前目录")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()

    print("MedAgentWork 环境检查")
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        error(f"Python 版本过低：{sys.version.split()[0]}，需要 3.10+")
    else:
        ok("Python 版本满足要求（>= 3.10）")

    check_skill()
    check_workspace(workspace)
    subject = check_materials(workspace)
    golden_count = check_golden_set(workspace)
    check_optional_deps()

    print("\n" + "=" * 56)
    print(f"结论: {'FAIL' if errors else 'PASS'}  错误={len(errors)} 警告={len(warnings)} 信息={len(infos)}")
    if errors:
        print("先修复 ERROR，再开始批次。")
    else:
        print_next_steps(workspace, subject, golden_count)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
