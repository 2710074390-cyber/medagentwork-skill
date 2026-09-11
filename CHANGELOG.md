# Changelog

本文件记录 MedAgentWork Skill 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 已知待办

- 拆分巨型文件：`scripts/render_review.py`（1520 行）、`scripts/gate_check.py`（1134 行）。
  前置条件：先为 `render_review.py` 补渲染快照测试作为回归基线（详见 v2.1 说明）。

---

## [v2.1] — 2026-09-12

依据《medagentwork-skill 仓库评审报告》（评审对象 v1.0 / commit `282af28`）逐条整改。
评审提出的 9 项 P1/P2 问题经本地核对**全部属实**，本版全部修复；另完成 5 项中期结构性改进。

### 修复（P1 确凿实现缺陷）

- **R1 死代码**：`check_r1_forbidden` 中 `not re.search(r'[（(]见上|见下|[）)]$', text)` 的
  第三个备选分支 `[）)]$` 在外层条件成立时必然为真，导致内层分支恒不可达
  （实测 `branch_reachable=False`）。改为 `not re.search(r'[（(]见[上文下][）)]', text)`
  并移除冗余内层 `if`，该分支恢复可达。
- **`scripts.telemetry` 死依赖**：包内不存在该模块，且 `scripts/` 无 `__init__.py`，
  故 `from scripts.telemetry import ...` 从来不可能成功。补齐 `scripts/telemetry.py`
  （零依赖 JSONL 事件日志，best-effort 不抛出），两处导入改为同目录导入；
  降级时打印警告而非静默吞掉 `ImportError`。
- **`medillustration_config` 缺失 + 字体路径写死**：补齐 `scripts/medillustration_config.py`
  （`load()` / `fonts()` / `canvas()`），提供**跨平台中文字体探测**
  （Windows / macOS / Linux 候选列表 + `MEDAGENTWORK_FONT_BOLD` 环境变量 + matplotlib 兜底），
  替掉 `annotate_image.py` / `render_diagram.py` / `compose_atlas.py` 中写死的
  `C:\Windows\Fonts\msyhbd.ttc`；字体不可用时抛出可诊断错误而非晦涩 `OSError`。
  其余脚本的静默 `except Exception: pass` 改为打印警告。
- **R2 文案与实现不符**：`rules_numeric.py` 中「显著长于其他选项(均{min_other}字)」
  实际取的是 `min(other_lens)` 而非均值，改为「最短{min_other}字」。

### 修复（P2 工程与分发）

- **`pipeline.yaml` 声明与实现脱节**：`subjects` 段剥离已废弃的 RAG 参数
  （`chunk_size` / `top_n` / `hybrid_search` / `keyword_weight`）；
  `runbook.patterns` 中引用的 `healthcheck.py` / `runbook.py` / `maintenance.py` /
  `sync_tools.py` 均未随包分发，改为只声明**真实存在能力**的故障处置表；
  `paper_assembly` 标记 `distributed: false` 并保留设计说明。
- **提示词正文路径残留**：5 个角色提示词正文完成路径清洗 ——
  `.dsh/skills/` → `references/`、`知识库素材/` → `输入素材/`、
  `subject_config.json` → `pipeline.yaml`、「豆包（Doubao）图片 Agent」→「外部生图 Agent（用户自备）」。
  文件头 NOTE 块重写为准确的清洗说明。正文残留归零。
- **冒烟测试不验规则命中**：新增 §11「规则命中断言」，构造 11 道探针题逐条断言
  R1 / R2 / R5 / R7 / R8 / R10 / R11 / R12 / R13 / JS1 **真的被触发**，
  另加 3 项专项断言（R1 死代码回归、R2 文案一致性、R8 词表配置驱动）。
  断言数 **10 → 23**。
- **缺少分发元数据**：新增 `requirements-optional.txt`（Pillow / PyYAML / jsonschema / jieba，
  各注明用途与降级行为）、`.github/workflows/ci.yml`
  （`compileall` + `pyflakes` + 冒烟测试 + 阈值可解析性，Python 3.10/3.12 矩阵）、
  `.gitignore`（屏蔽 `__pycache__/`、`smoketest/test_ws/`、`reports/`）。

### 新增（中期结构性改进）

- **`pipeline.yaml` 成为真正的单一事实来源**：新增 `thresholds:` 段集中全部可调阈值；
  新增 `scripts/pipeline_config.py` 零依赖加载器
  （PyYAML → 内置最小解析器 → 内置默认值三段式）。R2 的 `2.0/1.5`、
  R13 的 `20/18`、GATE-A3 的 `15%` 全部改为**运行时读取**，消除配置双轨制。
  因保留内置默认值，未安装 PyYAML 的零依赖环境行为完全不变。
- **R8 豁免词表接入配置**：由 `thresholds.r8_legit_terms_default` + 按科目叠加
  （`tcm` / `surgery` / `psychiatry`）驱动，科目取自题目 `subject` 字段或
  `MEDAGENTWORK_SUBJECT` 环境变量。默认值与原精神科词表一致，默认行为零回归。
- **Bloom 独立重算交叉验证**（新增子门禁 `GATE-A3-BLOOM-RECOMPUTE`）：
  门禁用题库 JSON 的 `bloom_level` 字段机械重算 Bloom 分布，与质检报告自述值比对，
  偏差 > `bloom_recompute_tolerance`（默认 5%）即 **BLOCKED**。
  将 Bloom 门禁从「读 LLM 自述」升级为「确定性重算 + 自述交叉验证」。
- **门禁语义边界声明**：`SKILL.md` 新增 §7.1「门禁保证什么、不保证什么」，
  表格化区分「确定性门禁」与「MedQC + 人工签收」两层质量，
  明确 D20 仍属 LLM 自述、仅 Bloom 做了重算、答案正确性最终责任在人工签收。
- **金标准冷启动支持**：`kaoyan_picker check` 新增 `--golden-absent` 显式降级模式
  （报告留痕 `degraded: true` + `golden_status`，打印醒目警告；不加该参数仍 fail-closed）；
  新增 `assets/golden_set_template.json`（10–20 题最小可用模板）；
  `SKILL.md` / `references/runbook.md` / `references/hard-constraints.md` 三处同步降级路径。
- **前置条件前置声明**：`SKILL.md` 顶部新增「两个前置条件」提示块
  （数据需自备 / 生图能力需自备，无生图能力请跳过插图阶段）。

### 变更

- `SKILL.md` 设计原则新增三条：「配置即事实来源」「Bloom 独立重算」「规则命中有测试」。
- `README.md` 补充依赖矩阵、配置与阈值说明、门禁边界说明、金标准降级说明、
  CI 说明与目录结构更新。
- `references/hard-constraints.md`：R13 标注阈值来源为 `pipeline.yaml`；
  HC-18 补充降级模式说明。

### 验证

- 冒烟测试：**23 passed / 0 failed**（v1.0 为 10 passed）
- `python -m compileall -q skills/medagentwork/scripts smoketest` 通过
- 屏蔽 PyYAML 后 `pipeline_config` 仍正确读出全部阈值
- Bloom 重算门禁实测拦截「题库真实 100% 记忆层 vs 质检报告自述 30/40/25/5」
  （报出最大偏差 70.0%）
- 金标准降级模式 exit code 符合预期（不加 `--golden-absent` → 1；加 → 0 + DEGRADED 警告）

### 未完成

- 评审 §七.8 建议的巨型文件拆分（`render_review.py` 1520 行 / `gate_check.py` 1134 行）**未做**。
  理由：属纯机械重构，且 `render_review.py` 尚无渲染快照回归基线，风险大于收益。
  建议下一版先补渲染快照测试再拆分。

---

## [v1.0] — 2026-09-11

首个公开发布版本。由 MedAgentWork 原项目转化而来，保留原版方法论资产，
剥离 RAG 检索、Cloudflare 部署、桌面生成器、跨工作区运维等与原项目耦合的部分。

### 新增

- **五阶段流水线**：MedMaster 编排 → MedGen 出题 → MedQC 质检 → MedFix 修复 → MedReview 成册
- **确定性门禁**：`GATE-A2/A3/A4/FINAL`，BLOCKED 即 halt 并回退（Orchestrator-as-Enforcer，HC-12）
- **机械化校验规则**：R1–R13 + B1 / JS1 / S3 专项（`scripts/validate/`）
- **Bloom 认知分层配额**：目标 记忆 30 / 理解 40 / 应用 25 / 分析 5，偏差 >15% 阻断
- **金标准比对**：真题配额 20%（合格带 15%–25%），引用题 100% 比对答案
- **NBME 反套路检测**：R10 词重复线索 / R11 收敛策略 / R2 长度比
- **教训入库**：`regression_db.json`（REG-001~015）+ HC-0~HC-19 硬约束，每条绑定真实事故批次
- **补丁溯源**：修复聚合文件必须同步源文件（HC-13），追溯日志强制 `source_file_synced`
- **交付渲染**：JSON 源 → MD 交付 → 可选 HTML（题库 / 复习资料 / 押题卷）
- **状态一致性**：状态只经 `workflow_state.py` 原子写（tmp + `os.replace`），禁手改（HC-17）
- **冒烟测试**：`smoketest/run_smoketest.py`，10 项断言覆盖「坏题阻断 → 修复 → FAIL==0 放行 → MD 导出」

### 说明

- 核心管线零第三方依赖（纯 Python 标准库）
- 不含任何真题、教材、图谱等第三方版权数据，由使用者自备
- MIT 许可

---

[Unreleased]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v2.1...HEAD
[v2.1]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v1.0...v2.1
[v1.0]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v1.0
