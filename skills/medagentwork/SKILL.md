---
name: medagentwork
description: 医学题库生产管线（五阶段 Agent 工作流：出题→质检→修复→成册），带确定性门禁校验、Bloom 认知分层配额、金标准比对与回归教训库。Invoke when 用户要从教材/笔记批量生成医学题库或复习资料、提到 MedAgentWork、题库生产、出题质检、押题卷、复习手册生成，或需要对已有题库做质量门禁校验。
---

# MedAgentWork — 医学题库生产管线

把教材/笔记变成高质量题库与复习手册的完整工作流。五个角色接力（MedMaster 编排 → MedGen 出题 → MedQC 质检 → MedFix 修复 → MedReview 成册），每个阶段转换由**确定性 Python 门禁**强制校验——门禁不通过，管线停止（Orchestrator-as-Enforcer，HC-12）。

本 skill 由 MedAgentWork 原项目转化而来，核心管线**零第三方依赖**（纯 Python 标准库），开箱即用。

> ⚠️ **两个前置条件（评审 §七.13 / §七.16）**
> 1. **数据需自备**：本 skill 只含**机制**不含**数据** —— 没有真题、教材、图谱。金标准（`GoldenSet/`）由你手动维护；无金标准时管线会走「降级模式」（见 §6）。
> 2. **生图能力需自备**：插图阶段（可选）的图片生成依赖**外部图片 Agent**（原「豆包」链路未随包分发）。没有该能力时请**跳过插图阶段**，其余阶段完全不受影响。

## 0. 定位与适用边界（先判断要不要用）

**定位**：一条**医学题库生产的工业流水线**（不是问答工具）——用 CI/CD 工程范式（Pipeline as Code + Quality Gate）治理 LLM 出题的不确定性。核心主张：**LLM 自检不可信，一切质量判定交给确定性脚本**。

| ✅ 适用 | ❌ 不适用 |
|---|---|
| 教材/笔记 → 系统化复习资料 + 配套题库 | 单题问答、临时查资料（流水线开销远大于收益） |
| 教研团队批量题库建设（需可追溯/可复现/可审计） | 需要医疗诊断建议（见 `Boundaries`） |
| 作为「LLM + 确定性门禁」工程范式的参考实现 | 无自有素材/金标准（本 skill 不含真题、教材、图谱） |
| 有自备真题/权威题库（`GoldenSet/`）的用户 | 想开箱即用出图（生图依赖外部图片 Agent） |

**三条最容易被高估的局限**（完整清单见仓库 `README.md` 的「局限性」一节）：

1. **门禁只保证形式质量，不保证临床正确性** —— 过了门禁 ≠ 题目正确（详见 §7.1）。
2. **只有 Bloom 一维做了独立重算** —— `D20` 等仍读 LLM 自述，门禁只保证「字段存在且非 0」。
3. **金标准是硬门槛** —— `HC-18` 要求每批 15%–20% 为金标准引用题；无金标准只能走降级，**该批次无兜底**。

## 1. 运行模型（先读）

两个目录，职责分离：

| 目录 | 位置 | 内容 |
|---|---|---|
| **本 skill 目录**（下文 `{SKILL}`） | 安装位置，只读 | 门禁脚本 `scripts/`、角色手册 `references/`、产物契约 `schemas/`、交付模板 `assets/`、管线配置 `pipeline.yaml` |
| **你的工作区** | 你自己的项目目录 | 素材输入、全部产物、状态文件（由本管线写入） |

**铁律：所有脚本必须在工作区目录下运行**（脚本按当前目录定位 `中间产物/`、`workflow_state.json` 等）：

```bash
cd <你的工作区>
python {SKILL}/scripts/validate_options.py --batch batch001
```

依赖：核心管线（validate/gate/state/qbank/fact_check/bloom/kaoyan/render）**零依赖**；插图四件套（render_diagram/annotate_image/export_webp/compose_atlas）需 `pip install Pillow PyYAML`。完整的可选依赖清单见仓库根目录 `requirements-optional.txt`。

**阈值调参**：所有可调阈值（选项长度上限、Bloom 偏差上限、R8 豁免词表等）集中在 `pipeline.yaml` 的 `thresholds:` 段，由 `scripts/pipeline_config.py` 在运行时读取（缺失回退内置默认）。改配置即全局生效，**不需要改 Python 代码**。

## 2. 工作区初始化（首次使用）

用户首次使用时，在用户工作区创建目录骨架：

```
输入素材/{科目}/      # 用户放入教材/笔记/重点（唯一人工输入）
中间产物/{batchID}/   # MedGen 题库 JSON + 备考资料
质检报告/{batchID}/   # MedQC 质检报告
最终产物/{batchID}/   # MedFix 修复版 + 追溯日志
复习资料/{科目}教学计划版/  # MedReview 主复习资料
GoldenSet/           # 金标准（仅用户手动维护，Agent 禁写）
archive/             # 签收归档
```

初始化状态文件（在 Python 中调用，或参考 `references/runbook.md`）：

```bash
cd <你的工作区> && python -c "import sys; sys.path.insert(0, '{SKILL}/scripts'); import workflow_state as ws; ws.save_state({'schema_version': 2})"
```

## 3. 管线总览

```
启动(登记批次) → MedGen 出题 → GATE-A2 → MedQC 质检 → GATE-A3
→ MedFix 修复 → GATE-A4 → MedReview 成册 → GATE-A5*
→ [插图阶段·可选] → 终审门禁 → 用户签收(APPROVED) → 归档
```

- 门禁 BLOCKED → **halt** → 回退对应角色修复 → 重跑门禁（不可跳过）
- **插图阶段（可选）需自备生图能力**：图片生成由**外部图片 Agent** 执行（原「豆包」链路未随包分发），本 skill 只产出「占位符 + 配图清单」。没有该能力时**直接跳过此阶段**，不影响其余流程与门禁。
- 每个阶段的完整角色手册在 `references/`，**进入该阶段前必读对应手册**：
  - `references/runbook.md` — 批次生命周期/门禁命令/目录规范/故障处置（编排必读）
  - `references/medmaster.md` — 编排规则与调用指令模板
  - `references/medgen.md` / `medqc.md` / `medfix.md` / `medreview.md` — 各角色执行规则
  - `references/medillustration.md` — 插图工作流（可选阶段）
  - `references/hard-constraints.md` — HC/D/R 硬约束全集（出题质检的规则底座）
  - `references/prompts/` — 五个角色的完整提示词（出题/质检的深度规范）

## 4. 批次生命周期（编排流程）

1. **启动**：用户说「开始新批次：{科目}+{章节}」→ 回显意图（科目/目标题数/模块划分/Bloom 目标）→ 用户确认 → 在 `workflow_state.json` 登记批次（批次号 `batch{NNN}`；`s, _ = ws.load_state(); b, _ = ws.ensure_batch(s, 'batch001'); b.update(subject=...); ws.save_state(s)`）
2. **MedGen**（读 `references/medgen.md` + `references/prompts/MedGen_current_prompt.md`）：读 `输入素材/{科目}/`，生成题库 JSON 写入 `中间产物/{batchID}/ALL_questions.json`（纯 JSON 数组），生成中每 50 题跑 Bloom 采样（HC-15）
3. **GATE-A2**（不可跳过）：validate FAIL==0 才放行；FAIL>0 → 打回 MedGen 修正
4. **MedQC**（读 `references/medqc.md` + 对应 prompt）：按 D1-D22 维度质检，报告写入 `质检报告/{batchID}/A3_质检报告.json`
5. **GATE-A3**：D20≠0 且 Bloom 偏差≤15%
6. **MedFix**（读 `references/medfix.md`）：按质检报告逐项修复，输出到 `最终产物/{batchID}/`（含追溯日志 `source_file_synced: true`）
7. **GATE-A4 + MD 导出**：复检 FAIL==0 后运行 `qbank.py export-md` 生成 `ALL_questions_FIXED.md`（最终交付格式）
8. **MedReview**（读 `references/medreview.md`）：生成教材浓缩型分层复习手册到 `复习资料/{科目}教学计划版/`
9. **终审**：`gate_check.py --stage final`（HC-9/10/11 + JSON 完整性）→ 用户审查 → 签收置 APPROVED → 用户手动把金标准题移入 `GoldenSet/`（仅用户操作）

## 5. 门禁命令速查

```bash
cd <你的工作区>

# 产出门禁（每个题库文件，MedGen 交付前自检 + GATE-A2）
python {SKILL}/scripts/validate_options.py --batch {batchID} --mode full   # FAIL==0 才放行

# 阶段门禁
python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent3_done   # GATE-A3
python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent4_done   # GATE-A4
python {SKILL}/scripts/gate_check.py --batch {batchID} --stage final         # 终审
python {SKILL}/scripts/gate_check.py --batch {batchID} --stage auto          # 自动检测当前阶段
python {SKILL}/scripts/gate_check.py --batch {batchID} --clear-halt          # 修复后清除 HALT

# Bloom 认知分层采样（目标 记忆30/理解40/应用25/分析5，偏差>15% 阻断）
python {SKILL}/scripts/bloom_sampler.py --batch {batchID} --threshold 15

# 事实校验（GATE-A2 前执行）
python {SKILL}/scripts/fact_check.py golden --file 中间产物/{batchID}/ALL_questions.json   # 金标准冲突检测
python {SKILL}/scripts/fact_check.py pages --file 中间产物/{batchID}/ALL_questions.json --subject {code}  # 页码锚点（无索引自动跳过）

# 金标准配额（真题占比，HC-18）
python {SKILL}/scripts/kaoyan_picker.py pick --subject {科目} --keywords "..." --target {题数×0.2} --out 中间产物/{batchID}/kaoyan_candidates.json
python {SKILL}/scripts/kaoyan_picker.py check --file 最终产物/{batchID}/ALL_questions_FIXED.json   # 占比≥15% 通过
# 确无金标准时（降级模式，会在报告中留痕 degraded=true）：
python {SKILL}/scripts/kaoyan_picker.py check --file 最终产物/{batchID}/ALL_questions_FIXED.json --golden-absent

# MD 导出（最终交付格式）
python {SKILL}/scripts/qbank.py export-md --file 最终产物/{batchID}/ALL_questions_FIXED.json --out 最终产物/{batchID}/ALL_questions_FIXED.md --title "{科目}·{模块}（{batchID}）"

# HTML 渲染（可选交付）
python {SKILL}/scripts/render_qbank_html.py --input 题库.json --output 题库.html --title "..."
python {SKILL}/scripts/render_review.py "复习资料/xxx.md"   # 自包含 HTML

# 状态与契约
python {SKILL}/scripts/workflow_state.py --show {batchID}
python {SKILL}/scripts/contract_check.py --batch {batchID}   # 产物 vs schemas 契约

# 插图占位一致性（配图科目，插图阶段后）
python {SKILL}/scripts/check_inline_images.py --md 复习资料/{科目}教学计划版/{科目}_主复习资料.md --img-dir 复习资料/{科目}教学计划版/images_webp --list 复习资料/{科目}教学计划版/{科目}_配图清单.md
```

门禁报告输出在 `reports/validate/` 与 `reports/gate/`。

> **GATE-A3 的两条 Bloom 检查**：① 自述偏差 ≤ `bloom_deviation_max`（默认 15%）；
> ② **独立重算交叉验证** —— 门禁会用题库 JSON 重算 Bloom 分布，与质检报告自述值比对，
> 偏差 > `bloom_recompute_tolerance`（默认 5%）即 BLOCKED（评审 §七.14 加固）。
> 子门禁 ID 为 `GATE-A3-BLOOM` 与 `GATE-A3-BLOOM-RECOMPUTE`。

## 6. 交付格式契约（HC-18）

| 产物 | 交付格式 | 说明 |
|---|---|---|
| 题库 | **JSON（机器可读源）+ MD（用户可读交付）** | MD 由 `qbank.py export-md` 生成，✅ 答案标记/解析/页码 |
| 复习资料 | MD（+ 可选 HTML：`render_review.py`） | 仅用站端渲染器子集，禁 Mermaid（用 ASCII 图） |
| 押题卷 | HTML（`assets/quiz_template.html` + QUESTIONS 数组） | 模板在 skill 的 assets/ |

- 复习资料 MD 附录必含：教材页码索引（真实页码禁占位）、术语同意异名对照表
- 复习资料 MD 仅用：h1-h6/表格/粗斜体/代码块/Obsidian Callout/`<details open>`/列表/hr；加粗用 `<b>`（导出兼容 E1-E3）

### 6.1 金标准（GoldenSet）冷启动与降级模式

HC-18 要求每批**至少 15%–20% 为金标准引用题**（`kaoyan_picker.py check` 判定），而 `GoldenSet/` 只允许用户手动维护。**没有自备真题的用户会卡在第一条 HC-18 门禁上**——这是本 skill 已知的最高门槛，因此显式定义降级路径：

| 情形 | 处理 |
|---|---|
| **有金标准**（推荐） | 把真题/权威题库放入 `GoldenSet/`；`kaoyan_picker.py pick` 按 20% 配额选题，`fact_check.py golden` 100% 比对答案 |
| **无金标准 · 首批** | 走**降级模式**：跳过 `kaoyan_picker pick`，并在 `kaoyan_picker check` 时**显式加 `--golden-absent`**。该模式会在报告里留痕 `degraded: true` + `golden_status: "absent(降级)"`，并打印醒目警告。**不加该参数时默认仍 fail-closed（占比不足即 FAIL）** —— 降级必须由操作者主动声明，不会悄悄放行。降级批次**没有金标准兜底**，答案正确性完全依赖 MedQC + 人工签收 |
| **无金标准 · 后续批次** | 建议先把已签收的高质量题（或公开指南衍生的自测题）**人工**移入 `GoldenSet/`，再开启金标准机制。可从 `assets/golden_set_template.json` 起步 |

**最小可用金标准模板**：见 `assets/golden_set_template.json`（10–20 题即可生效）。字段与 `kaoyan_picker.py --upper/--lower` 期望的输入一致：`gs_id` / `year` / `question_no` / `type` / `stem` / `options` / `answer` / `explanation` / `subject` / `source_file`。默认路径约定为 `GoldenSet/structured/GS_上册_*.json`（题干）+ `GoldenSet/structured/GS_下册_*.json`（答案解析）。

> 降级模式是**有意识的取舍**，不是"门禁失效"：它明确告诉你"这批没有金标准兜底"，而不是悄悄放行。

## 7. 关键设计（为什么这样做）

- **门禁即防线**：LLM 自检不可信，一切质量判定交给确定性脚本（5 起管线绕过教训的结论）
- **教训入库**：`regression_db.json`（回归漏洞库）+ `references/hard-constraints.md`（HC-0~HC-19 硬约束）——每次事故都沉淀为可机械执行的规则
- **Bloom 配额**：认知分层目标 30/40/25/5，实时采样防「记忆层超标」
- **结构模板优于字数约束**：选项长度靠「每题选项共享相同语法结构」而非 min/max 字数（3 次振荡教训）
- **NBME 反套路**：R10 词重复线索 / R11 收敛策略 / R2 长度比等机械化检测，防 LLM 出题的隐性泄题
- **补丁溯源**：修复聚合文件必须同步源文件（HC-13），追溯日志 `source_file_synced` 强制
- **配置即事实来源**：所有阈值集中在 `pipeline.yaml` 的 `thresholds:` 段，由 `scripts/pipeline_config.py` 运行时读取（零依赖，缺失回退默认）——改配置即全局生效，不再有"声明与实现双轨"
- **Bloom 独立重算**：门禁不采信质检报告的 LLM 自述分布，而是从题库 JSON 重算并交叉验证（偏差 > 5% 即 BLOCKED）——把 Bloom 门禁从"读 LLM 自述"升级为"确定性重算"
- **规则命中有测试**：冒烟测试不仅验"脚本可执行"，还断言 R1–R13/JS1 每条规则**真的被触发**（防止 R1 那类死代码再次溜过）

## 7.1 门禁保证什么、不保证什么（边界声明，必读）

**这是本 skill 最容易被高估的一处**：过了门禁 ≠ 题目在临床上正确。请严格区分两层质量。

| | 门禁（确定性脚本） | MedQC（LLM）+ 人工签收 |
|---|---|---|
| **保证** | ✅ 形式合规：长度/单位/重复词/分布/JSON 结构/文件存在性/契约字段 | ✅ 语义质量：答案在临床上对不对、解析是否自洽 |
| **不保证** | ❌ 不判断临床正确性、不判断解析是否成立、不判断题目是否有教学价值 | ❌ 不保证机械规则全过（仍需跑门禁） |
| **证据来源** | 脚本重算题库数据（**确定性**） | 质检报告中的 LLM 自评（**自述数据**） |

具体说明：

- 门禁判定的是**形式质量**。R1–R13 检查的是选项长度、单位缺失、重复词、认知层级分布等**可机械判定**的特征，它无法判断"这道题选 A 对不对"。
- `GATE-A3` 的 **D20 分数**读自 `A3_质检报告.json`，仍属 LLM 自述；门禁只保证「字段存在且非 0」（fail-closed），不保证分数真实。
- `GATE-A3` 的 **Bloom 分布**已做加固（v2.1）：门禁会用题库 JSON **独立重算** Bloom 分布，与质检报告自述值交叉验证，偏差 > `bloom_recompute_tolerance`（默认 5%）即 BLOCKED。这条堵住了"LLM 填一个漂亮的分数"，但**只有 Bloom 这一维**做了重算。
- **答案正确性的最终责任人是你（人工签收）**。金标准比对（`fact_check.py golden`）只能覆盖有真题的那 20% 配额。

一句话：**门禁是"防呆"，不是"防错"。它挡得住格式崩坏与自述造假，挡不住内容本身是错的。**

## 8. 与原版的差异（缩减说明）

| 原版特性 | skill 版处理 |
|---|---|
| RAG 知识库检索（向量+重排序） | 缩减：直接读 `输入素材/` 文件；如需检索增强由宿主 agent 自行接入 |
| 考研真题库内容 | 机制保留（`kaoyan_picker.py`，支持 `--upper/--lower` 自定义金标准），真题数据用户自备（版权） |
| 人体解剖图谱复用 | 机制保留（`compose_atlas.py`），图谱素材用户自备（版权） |
| Cloudflare 站点部署 / 访问计数 | 不含（线上站与本地管线无关） |
| MedKit 桌面生成器 | 不含（独立仓库） |
| DSH subagent 编排 | 通用化：单会话顺序执行各阶段（宿主支持 subagent 时可并行） |
| 跨工作区运维（maintenance/healthcheck） | 不含（原项目专属运维） |
| 组卷器（paper_builder.py）与难度校准数据 | 不含（依赖用户自备真题；`pipeline.yaml` 中仅留设计说明） |
| `pipeline.yaml` 中的 RAG / 运维脚本声明 | 已清理（v2.1）：移除未分发的 `chunk_size/top_n/hybrid_search` 与 `runbook.patterns` 脚本引用，改为只声明真实存在的能力 |

## Boundaries

- ❌ 不提供医疗诊断 — 仅基于已发表文献出题/质检
- ❌ 不编造研究结果 — 没有就说"未检索到"
- ❌ 不修改 GoldenSet — 金标准由用户手动维护
- ❌ 不跳过门禁 — 阶段转换必须跑脚本验证
- ❌ 不手改 workflow_state.json — 走 `workflow_state.py`（HC-17）
- ✅ 可以：出题、质检、修复、追溯、成册、统计
