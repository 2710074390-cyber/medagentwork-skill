# MedAgentWork 批次运行手册

> 本文改编自原项目 medbatch skill。`{SKILL}` = 本 skill 安装目录；所有命令须在**用户工作区**目录下执行。

本手册定义一个批次从启动到签收的全部规则。编排者（MedMaster）在每个批次开始时加载并逐条执行。

## 1. 批次生命周期

```
启动(登记批次) → 阶段2 MedGen → 门禁A2 → 阶段3 MedQC → 门禁A3
→ 阶段4 MedFix → 门禁A4 → 阶段5 MedReview → 门禁A5
→ 终审门禁 → 用户签收(APPROVED) → 归档
```

- 门禁未通过 → **halt** → 回退对应角色修复 → 重跑门禁（不可跳过，HC-12）
- GoldenSet 签收只由用户手动执行，任何角色禁止写入
- 门禁A5：MedReview 产出主复习资料 MD，编排者核对 MD 结构完整（标题层级/模块划分/附录齐全）
- **门禁A5 附加（HC-20/D0 · 2026-10-18，有教师重点/复习大纲输入的批次强制）**：跑 `python {SKILL}/scripts/check_keypoint_coverage.py --keypoints <教师重点原文> --md <主复习资料 MD>`（数值/时间窗类硬事实缺失或重点条目缺 `📌 重点原文（第X条）` 落点 → exit 1 → 回退 Agent 5 补写；无教师重点输入 → `SKIPPED` 退出码 2，**不视为通过**）
- **门禁A5 附加（HC-26 详细度 · 2026-10-27）**：跑 `python {SKILL}/scripts/check_review_detail.py --md <主复习资料 MD> --mode auto --profile release_teacher_keypoint`（槽位/八块/自测答案任一不达标 → exit 1 → 按 `cards[].missing_slots` 返工）。**先覆盖、再展开、最后自测**；交付物必须是合并后的单一 MD
- **门禁A2 附加（HC-27 概念标注）**：`schema_version=2.1` 的批次在 MedGen 交付前自跑 `check_source_concepts.py`；旧批次返回 SKIP，不视为通过
- **阶段化推进（HC-25）**：新批次/新版本按 R0→R1→R2→R3→R4 推进并在 `reports/gate/` 留结论（PASS/WARN/BLOCKED/SKIPPED）；**SKIPPED ≠ PASS**，详见 `references/quality-gate.md`

## 2. 目录与命名（铁律）

| 阶段 | 目录 | 产物命名 |
|---|---|---|
| 输入 | `输入素材/{科目}/` | 用户放入教材/笔记；教师重点建议命名为 `{科目}_教师重点_<学校或日期>.md` |
| Agent 2 | `中间产物/{batchID}/` | `ALL_questions.json`、备考资料 .md |
| Agent 3 | `质检报告/{batchID}/` | `A3_质检报告.json` |
| Agent 4 | `最终产物/{batchID}/` | `ALL_questions_FIXED.json`、**`ALL_questions_FIXED.md`（最终交付格式，强制）**、`AGENT4_追溯日志.json`、`AGENT4_修改声明.md`、`escalations_for_human.md` |
| Agent 5 | `复习资料/{科目}教学计划版/` | `{科目}_主复习资料.md` |
| 金标准 | `GoldenSet/` | 仅用户手动移入 |
| 归档 | `archive/{类别}/{batchID}/` | 签收后归档（手动移动） |

批次号格式 `batch{NNN}`（如 batch026）；子批用 `batch026-A/B/C` 时必须在 workflow_state 中登记说明。

## 3. 门禁命令（每个阶段转换前强制执行）

```bash
cd <工作区>

自检      python {SKILL}/scripts/doctor.py --workspace <工作区>   # 首次使用/环境复核
GATE-A2   python {SKILL}/scripts/validate_options.py --batch {batchID} --mode full   # FAIL==0 才放行；仅 WARN 退出 0（不阻断）；文件/数据错误退出 2
GATE-A3   python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent3_done
GATE-A4   python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent4_done
MD导出    python {SKILL}/scripts/qbank.py export-md --file 最终产物/{batchID}/ALL_questions_FIXED.json --out 最终产物/{batchID}/ALL_questions_FIXED.md --title "{科目}·{模块}（{batchID}）"
金标准配额  python {SKILL}/scripts/kaoyan_picker.py check --file 最终产物/{batchID}/ALL_questions_FIXED.json   # 占比≥15% 通过
            无金标准时显式降级：追加 --golden-absent（报告留痕 degraded=true）
重点覆盖  python {SKILL}/scripts/check_keypoint_coverage.py --keypoints "输入素材/{科目}/{科目}_教师重点_<学校或日期>.md" --md "复习资料/{科目}教学计划版/{科目}_主复习资料.md"   # HC-20/D0（--keypoints 按实际文件名传入，脚本不展开 * 通配符；exit 1 → 回退 Agent 5 补写；无教师重点输入 → SKIPPED）
详细度    python {SKILL}/scripts/check_review_detail.py --md 复习资料/{科目}教师重点版/{科目}教师重点版_主复习资料.md --mode auto --profile release_teacher_keypoint   # HC-26（门禁A5 与终审前各跑一次；enforce FAIL → 返工）
视觉/排版 python {SKILL}/scripts/check_review_visual.py --md 复习资料/{科目}教师重点版/{科目}教师重点版_主复习资料.md --profile release_teacher_keypoint   # V1–V5/V14；规范见 review-visual-spec.md
学习价值  python {SKILL}/scripts/check_learning_value.py --file 最终产物/{batchID}/ALL_questions_FIXED.json   # HC-24（schema 2.0 批次；FAIL>0 不得交付）
概念标注  python {SKILL}/scripts/check_source_concepts.py --file 最终产物/{batchID}/ALL_questions_FIXED.json --batch {batchID}   # HC-27（schema 2.1 批次；旧批次 SKIP）
概念图    python {SKILL}/scripts/check_concept_graph.py --subject {科目}   # C1–C8（需 KC 注册表；单科约 0.4s）
终审      python {SKILL}/scripts/gate_check.py --batch {batchID} --stage final
```

- 已签收（APPROVED）批次重跑门禁只作参考，不写 HALT
- `python {SKILL}/scripts/gate_check.py --batch {batchID} --clear-halt` 清除该批次 HALT（修复后使用）
- validate 报告输出在 `reports/validate/`，gate 报告在 `reports/gate/`
- **MD 导出是最终交付格式**：GATE-A4 通过后必须运行 export-md（JSON 为机器可读源，MD 为用户可读交付），与 JSON 同目录交付
- **金标准配额（HC-18）**：批次启动前运行 `kaoyan_picker.py pick`（检索该章节真题候选，注入 MedGen 调用指令）；终审前运行 `check`（占比 ≥15% 通过）。
  - 确无真题覆盖时**显式降级**：`check ... --golden-absent` → 报告留痕 `degraded: true` + `golden_status: "absent(降级)"`，并打印醒目警告。**不加该参数默认 fail-closed（占比不足即 FAIL）**，降级必须由操作者主动声明。
  - 降级批次**没有金标准兜底**，答案正确性完全由 MedQC + 人工签收负责 —— 请据此调整信任预期。
  - 最小可用金标准模板：`{SKILL}/assets/golden_set_template.json`（10–20 题即可生效）。
- **教师重点覆盖（HC-20/D0 · 2026-10-18）**：有教师重点/复习大纲输入的批次，Agent 5 交付前必须产出 `中间产物/{batchID}/{科目}_教师重点覆盖矩阵.md`（未覆盖/部分覆盖行数=0）；编排者在门禁A5 与终审前跑 `check_keypoint_coverage.py`，数值/时间窗/分级界值缺失或重点条目缺 `📌 重点原文（第X条）` 锚点 → exit 1 → 回退 Agent 5 补写（batch039 突发性聋时间窗丢失教训）。

### 门禁输入字段形状契约（2026-10-19 加固 · 防门禁误判）

> 实证：三处「下游产物字段形状 ≠ 门禁解析形状」会导致门禁假 BLOCKED（内容本身合格），须由编排者在跑门禁前核对。

| 产物字段 | 门禁解析形状 | 常见错误形状 | 后果 |
|---|---|---|---|
| `A3_质检报告.json` → `bloom_distribution.actual` | 扁平百分数 或 `{"actual":{...}}` / `{"actual_pct":{...}}` | `{"记忆":{"count":n,"ratio":r}}` 嵌套计数 | GATE-A3（BLOOM / BLOOM-RECOMPUTE）误判自述 0.0% → BLOCKED |
| `AGENT4_追溯日志.json` → `source_file_synced` | **顶层** `source_file_synced`/`source_files_synced`（或 `patches[]` 全员 true） | 写在 `execution_metadata` 内部 | GATE-A4-HC13 误判 false → BLOCKED |
| 主复习资料 MD → `📌 重点原文（第X条）` | `--keypoints` 文件的连续编号，落点行逐字照录该条原文 | 沿用来源文档印刷标号（源文档常跳号/重号） | 落点整体错位 → `partial_facts` 失败 |

**编排者动作**：GATE-A3/A4 前先按上表核对形状；不符时**先判明是「形状不符」还是「内容不合格」**——形状不符可归一化（须留痕），内容不合格必须回退重做。

### 押题卷交付（2026-10-19 · HC-18 修订）

> 押题卷**交付形态由 HTML 改为 MD**（供刷题软件导入）。

- **题型归一为三标签**：`单选题` / `多选题` / `判断题`；题目标题 `### N. [单选题|多选题|判断题｜Bloom] qid`，必须含 `**答案：X**` 行
- **HTML 交付已下线**（`assets/quiz_template.html` 仅历史遗留，不再产出）
- 押题卷不参与批次端到端生命周期（可对已签收批次按需组卷）；MD 进交付目录前必须过 `verify_produce_rules.py`；PDF 一律人工导出上传

### 事实校验（P1-1 · GATE-A2 前执行）

```bash
python {SKILL}/scripts/fact_check.py pages --file 中间产物/{batchID}/ALL_questions.json --subject {code}
python {SKILL}/scripts/fact_check.py golden --file 中间产物/{batchID}/ALL_questions.json
```

- `pages` FAIL（P0 占位符/页码越界）→ 打回 MedGen 修正页码锚点
- `golden` 冲突（术语相似但数值不一致）→ 人工核对后裁决
- 科目缺分块索引时 pages 自动跳过（提示 WARN，不阻断）

## 4. 状态与记忆

- `workflow_state.json`：批次状态/步骤/血缘/门禁结果。由编排者或 ingest/save/gate_check 更新，**子代理不得直接改写**（HC-17，统一走 `workflow_state.py`）
- 批次关键事件（启动/门禁/halt/签收）建议记入工作区 `memory/JOURNAL.jsonl`（UTF-8 JSONL，一行一条）
- 新教训 → 更新 `references/hard-constraints.md`；完成项 → 更新工作区 `docs/TODO.md`

## 5. 常见故障处置

| 症状 | 处置 |
|---|---|
| 门禁 BLOCKED | 读 gate 的 reason → 回退对应角色修复 → 重新运行门禁 |
| JSON 解析失败 / YAML 前置 | 要求角色输出纯 JSON 数组，元数据单独 .md（batch006 教训） |
| 教师重点覆盖门禁报“原文不存在”/ exit 2 | `--keypoints` 传入实际文件名（不是 `*`）；建议命名 `{科目}_教师重点_<学校或日期>.md`；多份重点先合并 |
| 视觉门禁 FAIL | 读 `review_visual_*.json` 的 `checks`；优先处理 `<details>`/Mermaid/`**`；再补 Callout（≥4/模块）、展开区（≥2/模块）、表格与三色标记；规范见 `references/review-visual-spec.md` |
| 选项截断/缺单位 | validate R7/R8/R9 → MedFix 修复，禁止暴力截断（batch014 教训） |
| Bloom 偏差 >15% | 回退 MedGen 按配额修正（`bloom_sampler.py`，HC-15） |
| 补丁未溯源 | 追溯日志缺 source_file_synced → 打回 MedFix（HC-13，batch014 教训） |
| 签收 | 用户确认 → 状态置 APPROVED → 用户手动移入 GoldenSet → 归档 |
| `qbank.py check` 报「文件不存在」 | 已归档批次属预期：`check` 已归档感知；如需持久化修正注册表路径用 `qbank.py rehome` |

## 6. 手工流程备用（save/ingest）

skill 版管线中各角色直接写文件，由编排者校验产物后更新血缘。`save.py` / `ingest.py` 保留给手工接力流程：

```bash
python {SKILL}/scripts/ingest.py <文件> --batch {batchID} --stage agent2   # 摄入产物并登记血缘
```
