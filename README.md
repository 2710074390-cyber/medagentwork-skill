# MedAgentWork Skill — 医学题库生产管线

把教材/笔记变成高质量题库与复习手册的 **AI Agent 技能**：五阶段工作流（出题 → 质检 → 修复 → 成册），每个阶段转换由确定性 Python 门禁强制校验，配 Bloom 认知分层配额、金标准比对、NBME 反套路检测与回归教训库。

**核心管线零第三方依赖（纯 Python 标准库），装好即用。**

由 [MedAgentWork](https://med-review-site.pages.dev) 项目转化而来，保留了原版全部方法论资产：HC-0~HC-19 硬约束（每条背后是一次真实事故）、D1-D22 质检维度、R1-R13 机械化校验规则、五个角色的完整提示词。

## 安装

技能采用通用 Agent Skills 格式（SKILL.md + scripts/ + references/），支持 TRAE 与 Claude Code。

**TRAE**：把 `skills/medagentwork/` 整个目录复制到你的工作区技能目录：

```
<你的复习资料项目>/.trae/skills/medagentwork/
```

**Claude Code**：复制到个人技能目录（全局可用）或项目技能目录：

```
~/.claude/skills/medagentwork/          # 全局
<你的复习资料项目>/.claude/skills/medagentwork/   # 单项目
```

**其他兼容环境**：任何支持 Agent Skills（SKILL.md）规范的宿主均可，将 `skills/medagentwork/` 放入对应技能目录即可。

**安装自检**（可选）：`python smoketest/run_smoketest.py` 会在临时工作区跑通「批次登记 → 坏题阻断 → 修复 → FAIL==0 放行 → MD 导出 → 规则命中断言」全链路（23 项断言），用于确认脚本在你机器上可用。

> **两个前置条件**
> 1. **数据需自备**：本 skill 只含机制不含数据（无真题/教材/图谱）。金标准由你手动维护，无金标准时走显式降级模式（见「金标准」一节）。
> 2. **生图需自备**：插图阶段（可选）依赖外部图片 Agent，未随包分发；没有该能力请跳过插图阶段，其余流程不受影响。

## 快速开始

1. 新建一个工作区目录（你的复习资料项目），放入教材/笔记：

   ```
   我的复习/
   └── 输入素材/
       └── 神经病学/
           ├── 第1章.md
           └── ...
   ```

2. 对你的 AI agent 说：

   > 加载 medagentwork 技能。开始新批次：神经病学+脑血管疾病，目标 50 题。

3. Agent 会回显批次计划（模块划分 / Bloom 目标 / 真题配额）→ 你确认后自动执行：出题 → 门禁校验 → 质检 → 修复 → 复习手册成册。任何门禁不通过，管线自动停止并回退修复——你拿到手的一定是通过全部校验的产物。

4. 交付物：`最终产物/{批次}/ALL_questions_FIXED.md`（题库，含 ✅ 答案标记）+ `复习资料/{科目}教学计划版/`（分层复习手册，可渲染 HTML）。

## 依赖

| 组件 | 依赖 | 说明 |
|---|---|---|
| 核心管线（validate / gate_check / workflow_state / qbank / fact_check / bloom_sampler / kaoyan_picker / render_qbank_html / render_review / contract_check / pipeline_config） | **无**（纯标准库） | Python 3.10+ |
| 插图四件套（render_diagram / annotate_image / export_webp / compose_atlas） | Pillow, PyYAML | 可选阶段，仅配图时需要 |
| schema 契约校验 | jsonschema | 可选，缺失时自动跳过 |
| R10/R11 分词精度增强 | jieba | 可选，缺失时回退 n-gram 滑窗 |

完整的可选依赖清单见 `requirements-optional.txt`：

```bash
pip install -r requirements-optional.txt
```

## 配置与阈值

所有可调阈值集中在 `skills/medagentwork/pipeline.yaml` 的 `thresholds:` 段，由 `scripts/pipeline_config.py` 在**运行时**读取（零依赖；未安装 PyYAML 时用内置最小解析器；读取失败回退内置默认值）：

```yaml
thresholds:
  r2_ratio_fail: 2.0              # R2 长度比 FAIL 阈值
  r2_ratio_warn: 1.5              # R2 长度比 WARN 阈值
  option_length_max: 20           # R13 单选项字数上限
  option_avg_max: 18              # R13 选项平均字数上限
  bloom_deviation_max: 15         # Bloom 单层偏差上限(%)
  bloom_recompute_tolerance: 5    # Bloom 独立重算与自述值的允许偏差(%)
  r8_legit_terms_default: [...]   # R8 短选项豁免词表（按科目可叠加）
  r8_legit_terms_tcm: [...]
```

改配置即全局生效，**不需要改 Python 代码**。可用 `python skills/medagentwork/scripts/pipeline_config.py` 核对当前生效值。

## 门禁保证什么、不保证什么

**过了门禁 ≠ 题目在临床上正确。** 请区分两层质量：

| | 确定性门禁（脚本） | MedQC（LLM）+ 人工签收 |
|---|---|---|
| **保证** | 形式合规：长度/单位/重复词/认知分布/JSON 结构/契约字段 | 语义质量：答案临床上对不对、解析是否自洽 |
| **不保证** | ❌ 不判断临床正确性、不判断解析是否成立 | ❌ 不保证机械规则全过 |

- `GATE-A3` 的 **D20 分数**读自质检报告，属 LLM 自述 —— 门禁只保证「字段存在且非 0」（fail-closed）。
- `GATE-A3` 的 **Bloom 分布**已加固：门禁用题库 JSON **独立重算**并与自述值交叉验证，偏差 > 5% 即 BLOCKED。**只有 Bloom 这一维做了重算。**
- **答案正确性的最终责任人是人工签收**；金标准比对只覆盖有真题的那部分配额。

## 金标准（GoldenSet）

HC-18 要求每批 15%–20% 为金标准引用题，而 `GoldenSet/` 只允许用户手动维护 —— **没有自备真题的用户会卡在这条门禁上**。因此提供显式降级路径：

```bash
# 有金标准（推荐）：放入 GoldenSet/structured/ 后
python {SKILL}/scripts/kaoyan_picker.py pick --subject <科目> --keywords "<词>" --target <题数×0.2> --out ...
python {SKILL}/scripts/kaoyan_picker.py check --file 最终产物/{batch}/ALL_questions_FIXED.json

# 无金标准：显式声明降级（报告中留痕 degraded=true，并打印醒目警告）
python {SKILL}/scripts/kaoyan_picker.py check --file ... --golden-absent
```

不加 `--golden-absent` 时默认 fail-closed（占比不足即 FAIL）—— 降级必须主动声明，不会悄悄放行。最小可用模板见 `skills/medagentwork/assets/golden_set_template.json`（10–20 题即可生效）。

## 目录结构

```
skills/medagentwork/
├── SKILL.md                 # 技能入口：管线总览 + 阶段调度 + 门禁速查 + 边界声明
├── references/              # 按需加载的角色手册与规则
│   ├── runbook.md           #   批次生命周期 / 门禁命令 / 故障处置
│   ├── medmaster.md         #   编排规则
│   ├── medgen.md            #   出题阶段执行规则
│   ├── medqc.md            #   质检阶段执行规则
│   ├── medfix.md            #   修复阶段执行规则
│   ├── medreview.md         #   复习资料成册执行规则
│   ├── medillustration.md   #   插图工作流（三通道路由）
│   ├── hard-constraints.md #   HC/D/R 硬约束全集（教训库）
│   └── prompts/             #   五个角色的完整提示词（路径已清洗为分享版）
├── scripts/                 # 全部门禁/状态/渲染脚本（纯标准库）
│   ├── pipeline_config.py   #   pipeline.yaml 阈值运行时加载器（单一事实来源）
│   ├── telemetry.py         #   JSONL 事件日志（可观测性，best-effort）
│   ├── medillustration_config.py  # 插图四件套配置源 + 跨平台字体探测
│   └── validate/            #   R1-R13 校验规则引擎
├── schemas/                 # agent2/3/4 产物契约
├── assets/                  # 押题卷 HTML 模板、成品页模板、金标准模板
└── pipeline.yaml            # 声明式管线配置（阶段/门禁/SLO/thresholds）
```

## 持续集成

`.github/workflows/ci.yml` 在每次 push / PR 时执行：语法编译检查（`compileall`）、静态检查（`pyflakes`）、冒烟测试（含规则命中断言）、`pipeline.yaml` 阈值可解析性验证。

## 使用约定

- **所有脚本必须在工作区目录下运行**（脚本按当前目录定位 `中间产物/`、`workflow_state.json` 等）：`cd <工作区> && python <技能目录>/scripts/xxx.py ...`
- 工作区目录（`输入素材/`、`中间产物/`、`质检报告/`、`最终产物/`、`复习资料/`、`GoldenSet/`）由 agent 首次使用时自动创建
- 金标准（GoldenSet）只允许用户手动维护——真题/权威题库由你自行放入，机制会按 20% 配额引用并 100% 比对答案一致性（支持 `--upper/--lower` 指定你自己的金标准 JSON）

## 与原版的差异

| 原版特性 | skill 版处理 |
|---|---|
| RAG 知识库检索（向量+重排序） | 缩减：直接读素材文件；检索增强由宿主 agent 自行接入 |
| 考研真题库内容 | 机制保留，数据用户自备（版权） |
| 人体解剖图谱复用 | 机制保留，图谱素材用户自备（版权） |
| Cloudflare 站点部署 / MedKit 桌面生成器 | 不含（与管线无关） |
| DSH subagent 编排 | 通用化：单会话顺序执行（宿主支持时可用 subagent） |
| 跨工作区运维脚本 | 不含（原项目专属） |

## 设计哲学（一分钟版）

- **门禁即防线**：LLM 自检不可信，一切质量判定交给确定性脚本
- **教训入库**：每次事故沉淀为可机械执行的规则（`regression_db.json` + HC 表），同类错误永不重犯
- **结构模板优于字数约束**：选项长度靠「每题选项共享相同语法结构」，而非 min/max 字数
- **NBME 反套路**：R10 词重复 / R11 收敛 / R2 长度比等机械化检测，防 LLM 出题的隐性泄题
- **补丁溯源**：修复必须同步源文件，杜绝「聚合文件修好了、源文件还坏着」
- **配置即事实来源**：阈值集中在 `pipeline.yaml`，运行时读取，不再有"声明与实现双轨"
- **Bloom 独立重算**：不采信 LLM 自述的认知分布，从题库重算并交叉验证
- **规则命中有测试**：冒烟测试断言每条规则真的被触发，而不是只验"脚本能跑"

## 许可

[MIT](LICENSE)。技能本体（文档、提示词、脚本、方法论）由原作者原创。
注意：skill 不含任何真题、教材、图谱等第三方版权数据——这些由使用者自备，且其使用需遵循相应版权方的授权条款。
