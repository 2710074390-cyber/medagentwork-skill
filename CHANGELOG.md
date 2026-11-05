# Changelog

本文件记录 MedAgentWork Skill 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v2.5] — 2026-11-06

> **防跳过门禁**：把「阶段门禁必须真跑」从提示词纪律变成**机械约束**。触发问题是「换一个
> agent 软件 / 模型，它不按 SKILL 里的命令跑，直接写交付物怎么办」——原项目的结论是
> **提示词不是约束**，因此本版把门禁执行做成交付物自己的属性（回执链 + 交付口拒收 + 审计），
> **与宿主无关**（不依赖任何宿主 hook，换 Claude Code / Codex / Cursor / WorkBuddy / Trae 都成立）。

### 新增

- `scripts/gate_run.py`：阶段门禁**唯一执行面**（`a2/a3/a4/lv/a5`）。preflight 先验上游回执（缺回执/断链/产物字节不符 → 执行前 `BLOCKED` 并给出下一步命令）→ 按阶段声明跑确定性门禁 → **PASS 才写回执**。阶段适用性由产物/状态机械判定（纯题库批次跳过 `a5`、纯复习资料批次跳过 `a2/a3/a4/lv`、schema<2.0 跳过 `lv`），并会按磁盘产物机械补写 `workflow_state` 的阶段步骤（`gate_check` 的 A3/A4 依赖 `steps.AGENT3/AGENT4`，此前无人写入）。`--stage all` 按适用阶段顺序执行。
- `scripts/gate_ledger.py`：回执链原语。`最终产物/{batch}/_gate_ledger.json` 把「产物字节 sha256 + 门禁执行摘要」按 `chain_prev` 链式绑定；删/改/插一条都会断链（`CHAIN_BROKEN`/`SEQ_MISMATCH`），产物被改过 → `ARTIFACT_MISMATCH`。
- `scripts/gate_audit.py`：工作区审计。`--batch`/`--all`/`--strict`；「产物在、回执不在」「回执链阶段顺序被重排」「签收批次缺阶段」「批次目录不是 batchNNN」判 FAIL；回执含 SKIPPED 子门禁 / `--golden-absent` 降级 → WARN。
- `scripts/qbank.py export-md` 新增**交付口验真**：输出落在 `最终产物/{batch}/` 时，验 A2/A3/A4（schema 2.0+ 含 lv）回执与阶段顺序 + A4 对输入 JSON 的字节绑定；缺回执/字节不符 → **exit 1，不生成交付 MD**。导出成功后追加 `export` 回执，把交付 MD 字节也绑定（导出后手改 MD → 审计 FAIL）。
- 冒烟测试新增 34 项防跳过断言：**真实跑通 a2→a3→a4→export 全链路**、缺上游/跳阶段 BLOCKED、`--dry-run` 不写回执、无回执交付拒收、篡改 JSON/MD 后拒收或审计 FAIL、删回执拒收、伪造回执断链、非 batchNNN 目录拒收、telemetry 签名回归。

### 变更

- `SKILL.md` 新增 §3.1「门禁不可跳过：回执链 + 单一执行入口」，§4 生命周期与 §5 命令速查改为以 `gate_run.py` 为唯一执行面（`validate_options/gate_check/check_*` 标注为内部实现，直跑不写回执）。
- `references/runbook.md` §3 改为「唯一执行面 + 内部实现」两节，新增 §3.2「回执链、交付口与审计」与故障处置行；`references/medmaster.md`、`references/quality-gate.md` 同步接线（HC-12 执行面收窄）。
- `README.md` 新增「门禁不可跳过（v2.5.0 防跳过层）」章节与目录结构/变更记录更新。

### 修复（本次验证中发现并修掉的既有缺陷）

- `scripts/telemetry.py`：`gate_check` 调用 `log_gate_check(..., reason=...)` 与签名不匹配，门禁内容 PASS 后仍抛 `TypeError` → `gate_check` 以 exit 1 结束，A3/A4/final 永远拿不到 PASS。改为接受 `**fields`。
- `scripts/workflow_state.py`：`migrate_legacy` 把 `state['halt']` 镜像里的 `batch_id` 当「误注入」剥掉 → `check_halt` 把它当历史全局 halt，**一个批次被 HALT 会误停所有批次**。现豁免 `halt`。
- `scripts/gate_check.py`：GATE-A4 要求交付 MD 已存在，而 MD 又要求 A4 回执 → **死锁**；MD 检查移到终审 `gate_final`（并加「MD 题数 = JSON 题数」一致性校验），A4 只验 JSON + 追溯日志。
- `scripts/validate/engine.py`：`最终产物/{batch}` 目录存在但为空时不再回退 `中间产物/`，导致 GATE-A2 误报「未找到批次题库文件」。

### 破坏性变更

- **交付口强制验回执**：v2.5 之前已在途的批次没有回执链，`qbank.py export-md` 写 `最终产物/{batch}/` 会被拒绝。**处理方式：重跑一次确定性门禁补齐回执**（`gate_run.py --stage a2 → a3 → a4`；门禁幂等，不需要回改产物）。
- **GATE-A4 不再要求交付 MD**（移到终审）：按旧文档「先 A4 再 export」的流程现在可正常走通；终审 `gate_check --stage final` 仍要求 MD 存在且题数一致。

### 验证

- 冒烟测试：**66 passed / 0 failed**（原 32 项 + 新增 34 项；含真实 a2→a3→a4→export 链路）。
- `python -m compileall -q skills/medagentwork/scripts smoketest` 通过。
- `python tools/preflight_publish.py --strict`：致命=0 警告=0。
- 独立对抗验证：篡改/删改回执、改产物字节、伪造单条回执、非规范批次目录均被拒或判红；本地伪造自洽回执属已知边界。

### 边界（诚实声明）

- 本地无法 100% 阻止伪造/绕开：有 shell 的 Agent 能自己 append 回执，也能**绕开 `export-md` 直接写文件**（此时只有 `gate_audit` 能事后发现）。本版保证的是「**跳过必留痕**（缺回执/断链/字节不符）+ **走 export-md 的交付必拒收** + **审计可复核**」，不是密码学防伪。
- 终审 `final` 读 `workflow_state` 自述字段（本 skill 流程不机械产生），**不纳入回执链**、不作交付前置；避免把诚实用户卡死。
- 回执是本机证据；跨机器/跨用户的复核依赖工作区是否随产物一并保留（本 skill 不假设 git/CI）。

### 并入 v2.5 —— 2026-11-02（原 Unreleased）

> 清除提示词层的插图残留。v2.2 已移除插图脚本与门禁，但三份提示词仍保留生图/配图清单指令，
> 形成「文档说已移除、提示词说怎么做」的口径矛盾。本次补齐，并以 `SOUL.md § HC-19（已下线）` 为准。

### 变更（破坏性）

- `references/prompts/Agent5_MedReview_Prompt.md`：删除「配图执行细则（V15）」整节与配图占位段，改为「不配图（HC-19 已下线）」声明；`## 输出、排版及配图` → `## 输出、排版`；交付与报告措辞去掉配图清单；V15 自检废止（编号保留不复用）。
- `references/prompts/MedMaster_current_prompt.md`：`AGENT6` 移出状态机；`### HC-19` 与 `### 阶段五·五：生图` 两节改为下线声明；终审第 6 条（插图完整性检查）改为「已取消」；终审汇总模板删除「插图：X 张」行。
- `references/prompts/MedQC_current_prompt.md`：D22（插图引用完整性）改为恒记 N/A，编号保留不复用；维度输出模板与 JSON 键同步。
- `scripts/quality_gate.py`：`BUNDLED` 集合与 R3 分支移除 `inline_images`（此前会路由到本包不存在的检查项）。
- `scripts/quality_policy.json`：`release_teaching_plan` 的 description 去掉「配图」字样。

### 说明

- 已交付含图历史产物不追溯、不回改；`references/review-visual-spec.md` 中「不要求配图 / 不生成插图」的否定表述保留。
- 需要旧插图能力仍请使用 [v2.1](https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v2.1)，本仓库不恢复该能力。
- 冒烟测试 `32 passed / 0 failed`。

### 并入 v2.5 —— 2026-10-31（原 Unreleased）

> 面向首次使用引导：装完即可自检、用内置 3 题示例跑通校验/导出，并把路径、命名与退出码口径统一到可执行状态。

### 新增

- 新增 `scripts/doctor.py`：检查 Python 版本、skill 完整性、工作区结构、`workflow_state.json`、输入素材命名、GoldenSet 与可选依赖，并输出下一步提示词。
- `init_workspace.py` 新增 `--example`：把内置 3 题示例复制到目标科目目录（`--subject`，缺省为 `示例科目`）、登记 `batch001`、生成 `示例运行说明.md`；已存在文件不覆盖。
- 新增 `assets/example_workspace/`：3 道已通过 R1–R13 的示例题 + 示例教师重点 + 教材摘录；`examples/minimal/` 同步为同一份可运行示例。
- `SKILL.md` 新增「§2.1 首次使用：Agent 必须执行的 5 步」，把环境自检、输入确认、初始化、金标准模式、批次回显变成强制引导流程。
- 冒烟测试新增首次使用链路断言（`--example` + `doctor.py` + 示例 validate），并新增 FAIL/WARN 退出码断言。
- 新增 `references/review-visual-spec.md`：复习资料视觉/排版单一事实来源，含设计 token、字体字号、卡片/表格/封面、颜色与无障碍、打印/PDF、Obsidian 基线、V1–V14 映射。
- 新增 `assets/review-visual.css`：可选 Obsidian CSS 片段/打印基线（单栏 760px、正文 15px/1.8、Callout、表格、A4 分页）。
- 新增 `scripts/check_review_visual.py`：机械检查 V1 三色覆盖、V2 Callout 密度/类型、V3 视觉呼吸、V4 展开区/禁用 `<details>`、V5 表格、V14 导出兼容；支持 `--advisory`。
- `quality_policy.json` 升级到 `1.3.0`，三个 profile 增加 `review_visual` 与 `visual_*` 阈值；`quality_gate.py` 接入 `r2.review_visual`。

### 修复

- `validate_options.py` 退出码口径与文档统一：**仅 FAIL>0 时退出 1；仅 WARN 时退出 0；文件缺失/未解析到题目退出 2**（此前 WARN>0 也退出 1，容易被误判为阻断）。
- README / examples 的安装路径统一为 `{SKILL}/scripts/...`，明确 `{SKILL}` = 包含 `SKILL.md` 的安装目录，修正手动复制/zip 导入后多套一层 `skills/medagentwork` 的路径错误。
- 教师重点命名统一为 `<科目>_教师重点_<学校或日期>.md`；`check_keypoint_coverage.py` 明确提示 `--keypoints` 按字面路径读取、不展开 `*`，并同步 SKILL/runbook/concept-layer/review-detail 命令。
- `SKILL.md` 对仓库根 `README.md` / `requirements-optional.txt` 的引用改为可选说明，只安装 `skills/medagentwork/` 时不再形成死链。
- **复习资料 `<details>` 口径统一**：SKILL.md / hard-constraints / medreview / Agent5 prompt 全部改为**禁用 `<details>/<summary>`**，展开区统一 `#### 🔬 展开：`；`check_review_visual.py` 对出现 `<details>` 直接 FAIL。
- **复习资料 HTML 口径统一**：明确 HTML 不是交付物，`render_review.py` 仅历史遗留，不参与管线/门禁/验收；Agent5 prompt 删除“HTML 由渲染器生成”的表述。
- `quality-gate.md` 补充 R2/R3 的 `check_review_visual.py` 映射，并修正“编排器不分发”的旧说明（分发版 `quality_gate.py` 已包含）。

### 验证

- 冒烟测试：**32 passed / 0 failed**（含 FAIL/WARN 退出码、`--example`、`doctor.py`、视觉门禁断言）。
- `python -m compileall -q skills/medagentwork/scripts smoketest` 通过。
- `python tools/preflight_publish.py --strict`：**致命=0 警告=0**。
- 仅复制 `skills/medagentwork/` 到临时目录后，`init_workspace.py --example` → `doctor.py` → `validate_options.py` → `qbank.py export-md` 全链路通过。
- 视觉门禁：合规样例 PASS；含 `<details>` / Mermaid / `**` 的样例 FAIL；`--advisory` 降级为 WARN 生效。

## [v2.4] — 2026-10-31

> 面向分发优化：下载后可在独立工作区初始化，使用者可以直接放入自己学校的考试重点和教材；补齐可移植的 R0–R4 质量门禁入口，并移除仅适用于原项目的发布检查依赖。

### 新增

- 新增 `skills/medagentwork/scripts/init_workspace.py`，一条命令创建工作区目录、状态文件和输入素材说明。
- 新增 `skills/medagentwork/scripts/quality_gate.py`，可在分发包内运行 R0–R4 阶段门禁。
- README 增加“本校考试重点”快速开始流程：换输入重点，不改管线。

### 修复

- 修正质量门禁脚本的路径基准：产物从当前工作区读取，规则、策略和 schema 从 skill 包读取。
- 移除分发版质量策略对原项目专属 baseline、KC 注册表、站点新鲜度和插图脚本的强制依赖。
- Claude 插件市场元数据版本更新为 `2.4.0`。

## [v2.3] — 2026-10-31

> 本版把原项目 2026-10-23 ~ 10-31 期间固化的规则线一次性对齐进 skill：HC-25 全流程质量基准、
> HC-26 复习资料详细度、HC-27 概念层、HC-22 真题双族配额，并补齐 HC-24 学习价值门禁脚本。
> 同时一并发布此前累积在 Unreleased 的 HC-20 / BPA v1.0 变更。

### 新增（HC-26 复习资料详细度 · 2026-10-27）

- **新增 `references/review-detail.md`** —— 详细度契约全文：三种输入模式（teacher_keypoint /
  course_schedule / module）、卡片九槽位 + 案例、分级量化下限与上限、反注水规则、模块八块、
  课程安排八块、门禁口径与单一文件交付要求。核心主张：**详细度不是字数，是「读一遍能否独立
  完成临床推理与应试判断」**。
- **新增 `scripts/check_review_detail.py`（836 行）+ `scripts/spaced_schedule.py` +
  `scripts/quality_policy.py` + `scripts/quality_policy.json` + `schemas/review_detail.schema.json`**
  —— 解析卡片九槽位/模块八块/课程自测对账，输出 PASS/WARN/FAIL 与逐卡 `missing_slots`、
  逐模块 `missing_blocks`；阈值从 `quality_policy.json` 读取（无 policy 时回退内置默认值）。
- `references/prompts/Agent5_MedReview_Prompt.md`：新增 **D6 详细度契约**（D6.1 九槽位 /
  D6.2 分级阈值 / D6.3 反注水 / D6.4 模块八块 / D6.5 课程安排八块 / D6.6 自检）、**V18 自检行**、
  行为约束第 20 条；标题升级为 v6.0 双版本说明。
- `references/medreview.md`：必读文件加 `review-detail.md`；执行规则新增 D6 与"单一文件交付"；
  完成报告新增 V18 项。

### 新增（HC-25 全流程质量基准 · 2026-10-23）

- **新增 `references/quality-gate.md`** —— R0 需求评审 → R1 开发实现 → R2 测试验证 →
  R3 发布上线 → R4 运行复盘；profile 与阈值表、门禁适用范围矩阵（题库/押题卷/复习资料）、
  阶段-脚本映射、WARN/BLOCKED/SKIPPED 口径与豁免规则、版本化与变更管理。
- `references/medmaster.md`：编排规则新增"阶段化推进（HC-25）"，必读文件加 `quality-gate.md`。
- `references/runbook.md`：生命周期与门禁命令表补 R0–R4 与各阶段附加门禁。
- `references/prompts/MedMaster_current_prompt.md`：新增 HC-25 五条编排规则 + 本 skill 可跑门禁清单。

### 新增（HC-27 概念层 · 2026-10-27）

- **新增 `references/concept-layer.md`** —— 一层三边的数据结构（KC 节点 / measures / prereq /
  ref + 模块级门控）、**每条边必须带 evidence** 的硬约束、从 `display_id` 重解析模块的陷阱、
  门禁 C1–C8 口径、概念卡命名铁律（学科前缀防同名歧义）、明确"本期不做"清单。
- **新增脚本**：`build_concept_graph.py`（建图 + 模块修正 + 无环校验）、`label_concepts.py`
  （三信号标注，有源标注走 declared）、`check_concept_graph.py`（C1–C8）、
  `build_concept_cards.py`（Obsidian 概念卡 + 索引 + MOC 回链）、`check_source_concepts.py`
  （HC-27 生成期 S1–S6 门禁）、`schemas/kc.schema.json`。
- `schemas/agent2_output.schema.json`：`schema_version` 增加 `2.1`；新增 `concepts` 与
  `learning_value` 属性；用 `if/then` 只在 2.1 下要求 `concepts`、A2/A3/A4/X `minItems=2`。
  **1.0/2.0 完全不受影响**。
- `references/prompts/MedGen_current_prompt.md`：新增 **HC-24 学习价值层** 与 **HC-27 概念标注**
  两节 + 阶段四自检附加三条。
- `references/medgen.md`：必读加 `concept-layer.md`；自检清单明确 `check_learning_value.py`
  与 `check_source_concepts.py`。

### 新增（HC-22 真题双族配额 · 2026-10-26 修订）

- `references/prompts/MedGen_current_prompt.md` / `MedMaster_current_prompt.md`：新增 HC-22 专节
  ——20% 考研 + 20% 执业医师、**按族结算**、族内多源可直接入选、`quota_status=reduced/cancelled`
  不阻断但要留 `reason`、三处标注（元数据 / `[源:…]` / `keypoint_ref`+`license`）、
  **不得把改编标成原题**、不得用 `--golden-absent` 绕过比例校验。
- `references/medgen.md`：配额规则新增第 8 条（双族口径 + 报告按族分列）。
- `schemas/agent2_output.schema.json`：新增 `zhiyi_origin`（含 `corpus=pdf_paper|cmexam`）。

### 新增（HC-24 学习价值门禁脚本）

- 补入 `scripts/check_learning_value.py` —— `references/medgen.md` 早已引用该脚本但未随包分发，
  本次补齐（R14 逐项覆盖 / R15 错误认知 / R16 引文实证 / R17 信息量 / R19 认知 ID 一致性 /
  answer 一致性）。

### 变更（脚本工作目录基准统一）

- 新分发脚本的 `BASE` 由 `Path(__file__).resolve().parent.parent` 统一改为 `Path.cwd()`，
  与 `bloom_sampler.py` / `fact_check.py` / `kaoyan_picker.py` 的口径一致：**脚本在用户工作区
  下执行，产物落 cwd**。`check_review_detail.py` 的 `--policy` 与 report schema 改为**随包定位**
  （`{SKILL}/scripts/quality_policy.json`、`{SKILL}/schemas/review_detail.schema.json`），
  离开原项目也能跑。

### 文档（对齐原项目 · HC-20 教师重点原文锚定 · 2026-10-18/19）

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

[v2.5]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v2.5.0
[v2.4]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v2.4
[v2.3]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v2.3
[v2.2]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v2.1...v2.2
[v2.1]: https://github.com/2710074390-cyber/medagentwork-skill/compare/v1.0...v2.1
[v1.0]: https://github.com/2710074390-cyber/medagentwork-skill/releases/tag/v1.0
