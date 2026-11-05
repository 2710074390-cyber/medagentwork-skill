# 全流程质量基准与阶段门禁（HC-25）

> 本文改编自原项目 `docs/质量管控规范.md`（v1.2.0 · 2026-10-27）。`{SKILL}` = 本 skill 安装目录；命令须在用户工作区执行。
> 单一事实来源：本 skill `scripts/quality_policy.json`（profile / 阈值）。
> 适用范围：所有**新批次、新版本、重新生成的产物**。已签收的旧批次与既有产物**冻结、不追溯、不回改**。

---

## 0. 三条底线

1. **旧产物不动**：已签收批次、已发布 PDF、既有题库与复习资料不因新标准被回改；如需增强，另开新批次或显式修订单。
2. **门禁不可跳过**：R0–R4 每个阶段必须有显式结论（PASS / WARN / BLOCKED / SKIPPED）；**SKIPPED 不等于 PASS**。批次阶段门禁由 `gate_run.py` 统一承载并在 PASS 后写回执（v2.5.0，防跳过；`a2/a3/a4/lv/a5`，终审 `final` 读自述状态不纳入回执链）；交付口验回执、`gate_audit.py` 事后复核——见 `references/runbook.md` §3.2。
3. **标准可执行**：每条标准必须绑定脚本、阈值、报告路径；不能只写在文档里。

---

## 1. Profile 与阈值

| Profile | 用途 | 默认模式 |
|---|---|---|
| `pilot` | 试点 / 研究性版本 | advisory |
| `release_teacher_keypoint` | 教师重点版正式发布 | enforce |
| `release_teaching_plan` | 教学计划版正式发布 | enforce |

阈值不在本文件写死——全部读取 `{SKILL}/scripts/quality_policy.json`。查看当前值：

```bash
python {SKILL}/scripts/quality_policy.py --show release_teacher_keypoint
python {SKILL}/scripts/quality_policy.py --validate     # 改阈值后必跑
```

**关键阈值（摘要，实际以 policy 为准）：**

| 指标 | pilot | release |
|---|---:|---:|
| KC 主映射率 | 100% | 100% |
| 教师重点覆盖 | 100% | 100% |
| 题目逐项覆盖 / 错误认知覆盖 | 100% | 100% |
| `source_quote` exact / 引文实证 | ≥95% | ≥95% |
| `misconception_id` 冲突 | 0 | 0 |
| anchor verified | warn <80% / block <70% | warn <90% / block <80% |
| 评分卡总分 | advisory ≥3.5 | enforce ≥3.8 |
| 关键维度（准确性/考点/溯源） | ≥3.5 | ≥3.5 |
| 蓝图最大相对偏差 | warn >20% / block >50% | 同左 |
| 复习资料详细度总分（HC-26） | advisory ≥80% | enforce ≥90% |
| 掌握级槽位完整率 | ≥85% | 100% |
| 卡片达标率 | ≥75% | ≥90%（教师重点）/ ≥95%（教学计划） |
| 自测答案覆盖 | ≥95% | 100% |
| 模块八块完整率 | ≥85% | 100% |

> 阈值是「新版本准入线」，不是对旧产物的追溯评价。

### 1.1 门禁适用范围矩阵

批次可在 `workflow_state.json` 显式声明 `product_types`（`question_bank` / `prediction_paper` / `review_material`，可多选）；缺失时由 `gate_check.py` 按产物形状推断。门禁只对具有管辖权的产物生效，避免「对题库查资料附录」一类假阻断。

| 门禁 | 题库 | 押题卷 | 复习资料 |
|---|---|---|---|
| GATE-A2 选项校验 | 必过 | 必过 | 不适用（SKIP） |
| GATE-A3 质检 + Bloom | 必过 | 必过 | 不适用（SKIP） |
| GATE-A4 修复溯源 + MD | 必过 | 必过（接受 `*押题*.md`） | 不适用（SKIP） |
| HC-24 学习价值层 | v2 必过 | v2 必过 | 不适用 |
| HC-9/10/11 资料附录 | 不适用 | 不适用 | 必过 |
| HC-26 复习资料详细度 | 不适用 | 不适用 | 必过 |
| 最终 JSON 有效性 | 必过 | 必过 | 不适用 |

- 不适用项必须在 `sub_gates` 显式记录 SKIPPED 及原因；**不得把 SKIP 当成 PASS**。

---

## 2. 生命周期 R0–R4

```
R0 需求评审 → R1 开发实现 → R2 测试验证 → R3 发布上线 → R4 运行复盘
```

| 阶段 | 输入 | 活动 | 通过条件 | 责任 |
|---|---|---|---|---|
| **R0 需求评审** | 教师重点/大纲、教材范围、出题蓝图、目标批次 | 明确范围/非目标、验收标准、风险、产物形态、是否需要 KC / 评分卡 / 学习价值层 | 必需输入齐全；范围/验收/风险已写；用户确认 | 用户 + MedMaster + 医学内容专家 |
| **R1 开发实现** | R0 确认的需求、教师重点、蓝图、既有脚本/契约 | 建/改 Schema 与数据契约；冻结基线；单元测试；**不修改源产物** | Schema 可解析；回归测试通过 | AI 工程 + 医学内容（规则） |
| **R2 测试验证** | R1 产物、题库、评分卡、KC 映射、复习资料 MD | 选项校验、质检、Bloom、学习价值、**详细度契约**、**视觉/排版**、概念图、内容专家抽检 | item FAIL=0；评分卡达标；详细度 ≥80%；视觉 V1–V5/V14 PASS；概念图 C1–C7 无 BLOCK | AI 工程 + 学习科学 + 医学内容 + 质量 |
| **R3 发布上线** | R2 通过版本、评分卡、产物形态 | 形态门禁、链接检查、发布说明、回滚方案、签收 | 评分卡 ≥3.8；详细度 enforce PASS；视觉 V1–V5/V14 PASS；形态全 PASS | MedMaster + 质量 + 用户 |
| **R4 运行复盘** | 线上/已交付版本、学习数据/反馈 | 健康检查、学习结果回收、问题归档、下一轮改进 | 无 P0 回归；反馈有记录；行动项进入下一轮 | MedMaster + 学习科学 + 用户 |

**各阶段红线：**

- **R0**：需求未确认不得进入 R1；不得用「先做再补需求」替代评审。
- **R1**：任何脚本不得写源题库/源复习资料；新产物落 `中间产物/` 或 `reports/`。
- **R2**：内容专家抽检不可省；FAIL 必须回退修复，不能「记录后放行」。
- **R3**：enforce BLOCKED 禁止发布；不允许用 `--advisory` 绕过正式发布；发布前必须能回滚。
- **R4**：学习效果未验证不得对外宣称「提升」。

---

## 3. 阶段与脚本映射（本 skill 已分发的能力）

| 阶段 | 自动检查 | 脚本 |
|---|---|---|
| R0 | 输入/规范存在、批次登记 | `workflow_state.py` |
| R1 | 契约可解析、状态一致 | `contract_check.py`、`ingest.py` |
| R2 | 选项校验、质检、Bloom | `validate_options.py`、`gate_check.py`、`bloom_sampler.py` |
| R2 | 题目学习价值（HC-24） | `check_learning_value.py` |
| R2 | 生成期概念标注（HC-27） | `check_source_concepts.py` |
| R2 | 概念图（C1–C8） | `check_concept_graph.py` |
| R2 | 复习资料详细度（HC-26） | `check_review_detail.py` |
| R2 | 复习资料视觉/排版（V1–V5 + V14） | `check_review_visual.py` |
| R2 | 自测答案对账 / 间隔调度 | `spaced_schedule.py` |
| R3 | 形态契约（HC-18） | `verify_produce_rules.py` |
| R3 | 教师重点覆盖（HC-20） | `check_keypoint_coverage.py` |
| R3 | 详细度 enforce | `check_review_detail.py`（`--profile release_*`） |
| R3 | 视觉/排版 enforce | `check_review_visual.py`（`--profile release_*`） |
| R4 | 学习结果 / 复盘 | `reports/` 人工归档 |

> 本 skill 已包含分发版 `quality_gate.py`（R0–R4 编排器），只检查本包实际提供的门禁；站点最新性、评分卡、KC 注册表等原项目专属检查不在包内。也可按上表逐条运行脚本，自行汇总 PASS/WARN/BLOCKED 到 `reports/gate/quality_gate_{batchID}_{stage}.md`。缺什么检查项，就在报告里显式写 SKIPPED 与原因。

**质量报告路径约定：** `reports/gate/quality_gate_{batchID}_{stage}_{timestamp}.json|md`
**证据保留：** 至少保留到下一版本发布 + 30 天；关键发布证据长期保留。

---

## 4. 例外、豁免与 SKIP

| 状态 | 含义 | 处理 |
|---|---|---|
| PASS | 满足阈值 | 进入下一阶段 |
| WARN | 不满足目标但未触及阻断线 | 记录原因、影响、补做计划；R2 可进 R3，但 R3 必须重新判定 |
| BLOCKED | 触及阻断线 | 禁止进入下一阶段；修复后重跑 |
| SKIPPED | 不适用 / 缺输入 | 必须写明原因；**不得当作 PASS**；R3 不接受关键项 SKIP |

**豁免规则：**

1. 只允许 WARN 豁免，不允许 BLOCKED 豁免。
2. 豁免必须写入报告：理由、影响范围、补做时间、责任人。
3. 同一问题连续两个版本 WARN → 自动升级为 BLOCKED（防「永久警告」）。
4. 旧批次不追溯；新批次/新版本不得引用旧批次的豁免。

---

## 5. 版本化与变更管理

- **标准版本**：`policy_version` 语义化。阈值/阻断线变化 → major；新增 WARN/检查项 → minor；文案/报告格式 → patch。
- **产物版本**：批次号 + 版本号（如 `batch041-v1`）；重新生成必须新版本，不得覆盖已签收版本。
- **变更流程**：提议 → 影响评估 → 更新 policy → 跑 R1/R2 验证 → 用户确认 → 生效。
- **回滚**：policy 变更必须保留上一版 `quality_policy.json` 的 Git 历史；发布回滚以版本为单位。

---

## 6. 与既有规则的关系

| 既有规则 | 关系 |
|---|---|
| HC-12 门禁强制 | HC-25 是 HC-12 在全流程层的扩展；阶段门禁仍由 MedMaster 执行 |
| HC-20 教师重点锚定 | R2 必查；R3 发布前必须 PASS；HC-26 不替代逐条覆盖 |
| HC-24 题目学习价值层 | R2 的 `learning_value` 检查；新批次 `schema_version=2.0` 强制 |
| HC-26 复习资料详细度 | R2/R3 的 `review_detail` 检查；标准见 `references/review-detail.md` |
| 复习资料视觉/排版 | R2/R3 的 `review_visual` 检查；标准见 `references/review-visual-spec.md` |
| HC-27 概念标注 | R2 的 `source_concepts` + `concept_graph` 检查；见 `references/concept-layer.md` |
| HC-18 产物形态 | R3 的 `verify_produce_rules.py` |
| HC-17 状态单一入口 | 门禁不写 `workflow_state.json`；状态推进仍走 `workflow_state.py` |
