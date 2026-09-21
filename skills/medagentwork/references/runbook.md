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

## 2. 目录与命名（铁律）

| 阶段 | 目录 | 产物命名 |
|---|---|---|
| 输入 | `输入素材/{科目}/` | 用户放入教材/笔记 |
| Agent 2 | `中间产物/{batchID}/` | `ALL_questions.json`、备考资料 .md |
| Agent 3 | `质检报告/{batchID}/` | `A3_质检报告.json` |
| Agent 4 | `最终产物/{batchID}/` | `ALL_questions_FIXED.json`、**`ALL_questions_FIXED.md`（最终交付格式，强制）**、`AGENT4_追溯日志.json`、`AGENT4_修改声明.md`、`escalations_for_human.md` |
| Agent 5 | `复习资料/{科目}教学计划版/` | `{科目}_主复习资料.md` |
| 金标准 | `GoldenSet/` | 仅用户手动移入 |
| 归档 | `archive/{类别}/{batchID}/` | 签收后归档（手动移动） |

批次号格式 `batch{NNN}`（如 batch026）；子批用 `batch026-A/B/C` 时必须在 workflow_state 中登记说明。

## 3. 门禁命令（每个阶段转换前强制执行）

```bash
cd <你的工作区>

GATE-A2   python {SKILL}/scripts/validate_options.py --batch {batchID} --mode full   # FAIL==0 才放行
GATE-A3   python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent3_done
GATE-A4   python {SKILL}/scripts/gate_check.py --batch {batchID} --stage agent4_done
MD导出    python {SKILL}/scripts/qbank.py export-md --file 最终产物/{batchID}/ALL_questions_FIXED.json --out 最终产物/{batchID}/ALL_questions_FIXED.md --title "{科目}·{模块}（{batchID}）"
金标准配额  python {SKILL}/scripts/kaoyan_picker.py check --file 最终产物/{batchID}/ALL_questions_FIXED.json   # 占比≥15% 通过
            无金标准时显式降级：追加 --golden-absent（报告留痕 degraded=true）
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
