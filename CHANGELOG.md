# Changelog

本文件记录 MedAgentWork Skill 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增（对齐原项目最新规则 · HC-20 教师重点原文锚定 · 2026-10-18/19）

- **HC-20 教师重点原文锚定与逐条覆盖**：教师重点/复习大纲原文 = **权威范围契约（下限）**，
  优先级**高于上游备考资料**；条目数值/时间窗/分级界值/剂量/百分比/并列与禁止结构须以
  **原文字面**落在对应考点，强制落点行 `📌 重点原文（第X条）：…`；交付前逐条覆盖矩阵
  「未覆盖/部分覆盖」行数必须为 0。落地到：
  - **新增 `scripts/check_keypoint_coverage.py`** —— 机械核验硬事实是否原样出现 +
    编号条目是否有落点行（含落点行上下文级核验，防"别处命中"假通过）。
    FAIL（退出码 1）→ 回退 Agent 5 补写，不得交付；无教师重点输入 → `SKIPPED`（退出码 2，**不视为通过**）。
  - `references/hard-constraints.md`：新增 HC-20 表条目 + 专节（定性 / 三条硬动作 /
    条号基准 / 原文锚定 > 原创性 / 机械化门禁）。
  - `references/medreview.md`：输入规则新增 D0 强制与条号基准；执行规则新增"覆盖矩阵"
    与 V17 自检报告；必读文件升级为 v5.6。
  - `references/medmaster.md`：门禁强制新增"有教师重点输入时门禁A5/终审前加跑 `check_keypoint_coverage.py`"。
  - `references/runbook.md`：生命周期新增"门禁A5 附加（HC-20）"；§3 门禁命令表新增"
    重点覆盖"一行。
  - `references/prompts/Agent5_MedReview_Prompt.md`：新增 **D0 节（最高优先·不可违反）**、
    **V17 自检项**、行为约束第 1 条（原文锚定例外）与第 18 条；输入来源优先级修订为
    **教师重点原文 > 备考资料 > 教材原文 > 修复后题库**；自检清单标题改为 `V1-V14 + V17`。
  - `SKILL.md`：§4 生命周期第 8/9 步、§5 门禁速查、§7 关键设计（新增"原文锚定优于概括"）。

### 变更（押题卷交付形态 HTML → MD · 对齐 HC-18 2026-10-19 修订）

- `references/hard-constraints.md` 产物形态契约：押题卷改为**仅 MD**（题型归一为
  **单选题/多选题/判断题**，供刷题软件导入），标注 HTML 交付已下线；补回
  **"PDF 一律人工上传、管线/脚本禁止生成"** 一行（此前 skill 版遗漏该硬约束）。
- `scripts/verify_produce_rules.py`：押题卷扩展名白名单改为 `{.md, .html}`（`.html` 仅提示不判 FAIL）；
  新增押题卷 MD 内容规则（题目标题 `### N. [单选题|多选题|判断题｜Bloom] qid`、必含 `**答案：X**`、无内部标记）。
- `SKILL.md` §6 交付格式契约表同步。

### 变更（门禁与工具加固 · 对齐 2026-10-19）

- `scripts/qbank.py` v1.3：与非活动条目（`status != 'active'`，即 superseded / source_archived）
  的重复降级为 **INFO**（不再计入 WARN"需人工裁决"）；完整性校验只针对 `active` 条目
  （已取代/源已归档条目其源文件按归档制度本就可能不在工作区）。
- `references/runbook.md` 新增 **「门禁输入字段形状契约」**：GATE-A3/A4 前核对
  `bloom_distribution.actual` / `source_file_synced` / `📌 重点原文` 三处字段形状，
  区分"形状不符（可归一化留痕）"与"内容不合格（必须回退）"，防门禁假 BLOCKED。

### 未纳入（有意排除，保持 skill 分享版边界）

- 插图管线（`HC-19` / `GATE-A6` / `medillustration` / 配图清单）——v2.2 已整体移除。
- RAG 检索（`search_kb.py` / `chunk_size` 等参数）与组卷器 `paper_builder.py` ——v1.0/v2.1 已缩减。
- 站点发布契约 `HC-21`、`check_site_freshness.py`、`deploy_site.ps1`、PDF 来源断言、
  `大四上` 分区门禁、跨工作区运维脚本 —— 均依赖原项目站点/部署设施，分享版不含。
- 导出保真 `E4`/`V16`（Obsidian 打印 CSS 与快照测试）——实现（`obsidian-snippets/`、`tests/`）未随包分发。

### 修复（分享版残留路径显式降级 · 评审清尾）

- `scripts/verify_page_numbers.py`：知识库索引清单（`知识库素材/index_store/index_manifest.json`）
  缺失时，`--subject` / `--all` 此前会抛出未捕获的 `FileNotFoundError`（traceback）；
  现改为报告 `SKIPPED` 并按非失败处理（exit 0）。页码索引属分享版可选能力
  （RAG 链路已剥离，索引随原项目自备），**附索引时的既有行为不变**；
  模块 docstring 同步补充「分享版说明」。
- `scripts/fact_check.py pages`：审计确认无索引路径**已有**显式降级
  （打印「教材分块索引不存在…跳过页码反查」后 exit 0），无需改动——仅记录审计结论。
- `README.md`：新增插图功能指引——插图管线自 v2.2 起整体移除，需要插图
  （图谱复用 / AI 底图 / 中文标注 / WebP 压缩）请使用
  [v2.1](https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v2.1)
  （插图功能最终维护版本）；「与原版的差异」表补回插图管线一行。

### 新增（分发能力）

- **具备自发布条件**，并补齐主流 Agent Skills 注册表要求的元数据：
  - 新增 `.claude-plugin/marketplace.json` → 任何人可
    `/plugin marketplace add 2710074390-cyber/medagentwork-skill` 直接安装（零审核）
  - `SKILL.md` frontmatter 按注册表规范补齐：`category: ai` / `risk: critical` /
    `source: community` / `date_added` / `author` / `license` / `tags`（5 个）/ `tools`
  - `SKILL.md` 新增 `## When to Use This Skill` 章节（原「§0 定位与适用边界」重命名，
    满足注册表必需章节的标题匹配）
  - `SKILL.md` 新增 `## Security & Safety Notes` 章节（`risk: critical` 要求：
    运行环境、写入范围、需要确认的动作、依赖安装、内容责任）
- 新增 `tools/preflight_publish.py`：把各渠道收录规范变成可执行预检
  （name/description 长度与保留字、name↔目录名一致、AAS 必需字段、
  `## When to Use` 章节、悬空链接、正文引用文件是否存在）。
  当前结果：**致命=0 警告=0**（`--strict` 亦通过）
- `README.md` 新增「分发与投稿」章节与多种安装方式（Claude Code 插件市场 /
  Vercel Skills CLI / 手动复制 / TRAE .zip 导入 / WorkBuddy 目录）

### 已知待办

- 拆分巨型文件：`scripts/render_review.py`、`scripts/gate_check.py`。
  前置条件：先为 `render_review.py` 补渲染快照测试作为回归基线（详见 v2.1 说明）。
- 若后续要投国际渠道（Claude / AAS），需补英文 README 与英文 description；
  并建议加最小示例数据集，让使用者装完能立刻跑通。

---

## [v2.2] — 2026-09-21

### 移除

- **移除全部插图相关功能**（图片文件、插图引用、相关代码与样式）：
  - 删除 7 个插图专属文件：`references/medillustration.md`、`scripts/annotate_image.py`、
    `scripts/check_inline_images.py`、`scripts/compose_atlas.py`、`scripts/export_webp.py`、
    `scripts/medillustration_config.py`、`scripts/render_diagram.py`
  - `scripts/render_review.py` 移除图片渲染代码与样式：`_replace_image()` 方法、
    `embed_images` 参数、`--embed-images` CLI 开关、`.med-figure`/`.fig-caption` CSS、
    `import base64`、插图张数统计；Markdown 图片语法改为剥离（不再输出 `<figure>`）
  - 管线移除插图阶段：`SKILL.md` / `runbook.md` / `medmaster.md` 的阶段图与目录约定、
    `references/hard-constraints.md` 的「插图生成分工」节、
    硬约束 HC-19（插图契约）、门禁 GATE-A6、Agent 6 状态（`AGENT6_INVOKED`/`AGENT6_DONE`）
  - 提示词移除插图规范：`Agent5_MedReview_Prompt.md` 的「插图规范」整节（57 行）与 V15 自检、
    `MedMaster_current_prompt.md` 的 HC-19 节与「阶段五·五：生图」节、
    `MedQC_current_prompt.md` 的 D22 维度（质检维度收敛为 **D1-D21**）
  - 依赖：`requirements-optional.txt` 移除 `Pillow`；`.gitattributes` 移除 `*.webp binary`
  - 说明：`PyYAML` **保留** —— 它同时是 `scripts/pipeline_config.py` 读取 `pipeline.yaml`
    的可选依赖，与插图无关

### 新增（文档）

- **README 新增三节介绍**，把"该不该用"的判断前置到安装之前：
  - 「这是什么（定位）」—— 一句话定位、管线示意、核心主张、以及**它不是什么**（4 条否定项）
  - 「适用场景」—— 适配良好 4 类 / 不适配 3 类，逐条给出原因
  - 「局限性（请先读）」—— 7 条按严重度排列的局限，每条对应具体代码或文档位置：
    ① 门禁只保证形式质量不保证临床正确性；② 只有 Bloom 一维做了独立重算；
    ③ 金标准是硬门槛、无金标准时机制价值归零；④ 不含任何版权数据；
    ⑤ 不提供 RAG 检索；⑥ 已知工程债（巨型文件未拆分、提示词语境残留、
    无原生并行）；⑦ 环境要求
- **`SKILL.md` 新增 §0「定位与适用边界」**：适用/不适用对照表 + 三条最容易被高估的局限，
  便于 Agent 在加载技能时先判断适用性；细节指向 README。

### 验证

- 冒烟测试：**23 passed / 0 failed**
- `python -m compileall -q skills/medagentwork/scripts smoketest` 通过
- `render_review.py` 实测渲染正常：输出 `<img>`=0、`med-figure`=0，
  粗体/表格/填空等正常内容完好（`<strong>`=1）
- **悬空引用扫描**：`annotate_image` / `check_inline_images` / `compose_atlas` / `export_webp` /
  `render_diagram` / `medillustration` / `GATE-A6` / `HC-19` / `AGENT6` / `embed-images` /
  `images_webp` / `Pillow` —— 除本 CHANGELOG 的历史条目外，命中 **0 个文件**
- 无脚本 import 已删除模块；`skills/` 文件数 **56 → 49**

### 说明

- `CHANGELOG` 的 v1.0 / v2.1 历史条目中保留插图相关记述（记录当时发布内容），
  属不可变历史记录，未作改写
- 本次为**破坏性变更**（功能与脚本删除、质检维度 D22→D21、硬约束 HC-19 移除）；
  按语义化版本本应升主版本号，依用户指定发布为 v2.2

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

- 评审 §七.8 建议的巨型文件拆分（`render_review.py` 1520 行 / `gate_check.py` 1255 行）**未做**。
  注：`gate_check.py` 在 v1.0 评审时为 1134 行，v2.1 因新增 Bloom 独立重算等逻辑增至 1255 行。
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

[Unreleased]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v2.2...HEAD
[v2.2]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v2.1...v2.2
[v2.1]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v1.0...v2.1
[v1.0]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v1.0
