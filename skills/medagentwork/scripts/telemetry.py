# -*- coding: utf-8 -*-
"""
telemetry.py — 管线可观测性事件日志（标准库实现，best-effort，永不阻断）

为什么有这个文件（评审报告 §6.5-P1.2）：
    此前 gate_check.py 与 validate/engine.py 都写着
        from scripts.telemetry import ...
    但包内不存在该模块，且导入路径本身也不成立（scripts 不是可导入包），
    于是靠 `except ImportError` 静默降级 —— 属原项目残留的死依赖，
    同时把真实的 ImportError 一起吞掉了。

    现按"补齐"而非"删除"处理：提供一个零依赖的 JSONL 事件日志实现，
    让 pipeline.yaml `observability` 段的声明落地；调用点改为显式失败可见。

输出：<工作区>/reports/telemetry/telemetry.jsonl（每行一个 JSON 事件）
失败策略：任何写入异常都只打印一行 stderr 警告，绝不抛出（可观测性不得阻断门禁）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

# 工作区 = 运行时 cwd（与其它脚本的 BASE 约定一致）
_WORKSPACE = Path.cwd()
_LOG_DIR = _WORKSPACE / "reports" / "telemetry"
_LOG_FILE = _LOG_DIR / "telemetry.jsonl"
_MAX_BYTES = 5 * 1024 * 1024  # 5MB 后轮转一次，避免无限增长
_ENABLED = os.environ.get("MEDAGENTWORK_TELEMETRY", "1") not in ("0", "false", "False")


def _emit(event: str, **fields) -> None:
    if not _ENABLED:
        return
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _MAX_BYTES:
            _LOG_FILE.replace(_LOG_FILE.with_suffix(".jsonl.1"))
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event}
        record.update({k: v for k, v in fields.items() if v is not None})
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # 可观测性失败不得影响主管线
        print(f"  ⚠️ telemetry 写入失败(忽略): {e}", file=os.sys.stderr)


def log_info(message: str, **fields) -> None:
    _emit("info", message=message, **fields)


def log_error(message: str, **fields) -> None:
    _emit("error", message=message, **fields)


def log_gate_check(batch_id: str, stage: str, status: str, details=None) -> None:
    _emit("gate_check", batch_id=batch_id, stage=stage, status=status, details=details)


def log_validation(filepath: str, mode: str, fail: int, warn: int, passed: int, summary=None) -> None:
    _emit("validation", filepath=filepath, mode=mode, fail=fail, warn=warn,
          passed=passed, summary=summary)


def log_event(event: str, **fields) -> None:
    """通用事件出口（供后续扩展，如 bloom_recompute / rule_hit）。"""
    _emit(event, **fields)
