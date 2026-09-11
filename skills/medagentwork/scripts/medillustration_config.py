# -*- coding: utf-8 -*-
"""
medillustration_config.py — 插图四件套的「单一配置源」（标准库实现）

为什么有这个文件（评审报告 §6.5-P1.3）：
    annotate_image.py / check_inline_images.py / export_webp.py / render_diagram.py
    四个脚本都 `from medillustration_config import ...`，但包内没有该模块，
    全部走 `except Exception: pass` 回退到硬编码默认值；其中
    annotate_image.py 的字体路径写死 `C:\\Windows\\Fonts\\msyhbd.ttc`，
    非 Windows 环境中文标注直接失败。

本模块提供三项能力：
    1. load()   —— 读取可选的 medillustration_config.yaml（缺失即用内置默认）；
    2. fonts()  —— 跨平台中文字体探测（Windows / macOS / Linux 候选列表 + 环境变量覆盖）；
    3. canvas() —— WebP 压缩等画布参数。

依赖策略：核心不引入第三方依赖。PyYAML 存在时解析 YAML；否则尝试同目录
    medillustration_config.json；再否则使用内置默认值。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

# ── 内置默认值 ──
_DEFAULT_CONFIG: dict = {
    "fonts": {
        # 留空表示交给 fonts() 自动探测
        "bold": "",
        "regular": "",
    },
    "canvas": {
        "webp_width": 1600,
        "webp_quality": 82,
        "webp_method": 6,
    },
    "gate": {
        "volume_kb": 500,
        "webp_only": True,
        "exempt_registry": None,
    },
}

# 跨平台中文字体候选（按优先级）
_FONT_CANDIDATES_BOLD = [
    # Windows
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux（常见发行版路径）
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]
_FONT_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

_cache: dict | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def load(force_reload: bool = False) -> dict:
    """读取插图配置：YAML（需 PyYAML）→ JSON → 内置默认。"""
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    loaded: dict = {}
    yaml_path = SKILL_ROOT / "medillustration_config.yaml"
    json_path = SKILL_ROOT / "medillustration_config.json"
    for path in (yaml_path, json_path):
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                loaded = json.loads(text)
            else:
                try:
                    import yaml  # type: ignore

                    loaded = yaml.safe_load(text) or {}
                except ImportError:
                    # 无 PyYAML：尝试同目录 JSON 兜底，否则用默认
                    if json_path.exists():
                        loaded = json.loads(json_path.read_text(encoding="utf-8"))
            if loaded:
                break
        except Exception as e:
            print(f"  ⚠️ 插图配置 {path.name} 解析失败，使用内置默认: {e}")

    _cache = _deep_merge(_DEFAULT_CONFIG, loaded if isinstance(loaded, dict) else {})
    return _cache


def _pick_font(candidates: list[str], env_var: str) -> str:
    """按「环境变量 → 候选列表首个存在项 → 首个候选」顺序确定字体路径。"""
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override
    for c in candidates:
        if Path(c).exists():
            return c
    # 最后尝试 matplotlib 自带字体管理器（若环境已装 matplotlib）
    try:
        from matplotlib import font_manager  # type: ignore

        for f in font_manager.fontManager.ttflist:
            if any(k in f.name for k in ("CJK", "Hei", "Song", "YaHei", "PingFang", "Noto")):
                return f.fname
    except Exception:
        pass
    return candidates[0]  # 交回调用方；调用方应在打不开时报出可诊断错误


def fonts() -> dict:
    """返回 {'bold': path, 'regular': path}，跨平台自动探测。"""
    cfg = (load().get("fonts") or {})
    bold = cfg.get("bold") or _pick_font(_FONT_CANDIDATES_BOLD, "MEDAGENTWORK_FONT_BOLD")
    regular = cfg.get("regular") or _pick_font(_FONT_CANDIDATES_REGULAR, "MEDAGENTWORK_FONT_REGULAR")
    return {"bold": bold, "regular": regular}


def canvas() -> dict:
    """返回画布/压缩参数 {'webp_width','webp_quality','webp_method'}。"""
    return dict(load().get("canvas") or {})


if __name__ == "__main__":
    print(json.dumps({"fonts": fonts(), "canvas": canvas()},
                     ensure_ascii=False, indent=2))
