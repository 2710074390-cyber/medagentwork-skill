# 概念层：从「题」到「概念」（CONCEPT · HC-27）

> 本文改编自原项目 `docs/概念层改造方案_v1.0.md` 与 HC-27 契约。`{SKILL}` = 本 skill 安装目录；命令须在用户工作区执行。
> 一句话：**把「题—知识点—前置」建成一层可门禁的数据结构**，让错题能归因到概念，概念能排出学习顺序。

---

## 0. 前置条件（没有就别跑）

| 依赖 | 路径 | 说明 |
|---|---|---|
| KC 注册表 | `中间产物/{batchID}/pilot/kc_registry.json`（或 `archive/中间产物/*/pilot/`） | 每科一份，含 `display_id / title / keypoints / pages / question_ids / status / metadata.blueprint_weights`。**没有注册表就没有节点，概念层无从谈起** |
| 题库 | `最终产物/{batchID}/ALL_questions_FIXED.json` | 概念标注与 measures 边的来源 |
| 教师重点锚定清单 | `输入素材/{科目}/{科目}_教师重点_<学校或日期>.md` | 提供 `keypoint_ref`，是 KC 与题之间的连接键 |

契约 Schema：`{SKILL}/schemas/kc.schema.json`。

---

## 1. 目标结构：一层三边

```
节点  KC（概念卡）：kc_id / display_id / module / title / keypoints / pages / weight / status
边①  measures  题 × KC，多对多，role=primary|differential|related，每条带 evidence
边②  prereq    KC → KC，单向，DAG，basis=page_order|module_order|manual
边③  ref       KC ↔ KC，无向，basis=same_keypoint|same_page
门控  module_prereq  模块 → 模块，这才是"能不能学下一模块"的硬门控
```

**边的证据规则（硬约束）**：每条边必须能回答「凭什么连」。

- `measures`：evidence = 该 KC 标题在题干/解析/逐项解析/teacher_anchor 中出现的原文片段；
- `prereq`：basis = `page_order`（同模块按教材页序相邻）或 `module_order`（模块链）；
- `ref`：basis = `same_keypoint`（共享教师重点条号）或 `same_page`；
- 答不出证据 → **不建这条边**。宁可图稀疏，不可图失信。

### 1.1 卡级前置 ≠ 学习门控

卡级 `prereq` 只是**阅读顺序**（同模块按页序连成一条链），链深等于卡数——把它当硬前置会出现「学第 85 张卡要先掌握 84 张」。真正的前置门控放在 **`module_prereq`**（模块级链，深度 = 模块数）。

### 1.2 已知陷阱

- **`module` 字段可能是坏的**：某些注册表把全部卡写成 `M00`，真实模块只在 `display_id`（`K-M01-001`）里。建图时**必须从 `display_id` 重新解析模块**，否则全库塌成一个模块（原项目实测 48 张卡全 `M00`）。
- **多标签是生成期属性，不是后处理属性**：题目按「一题一锚点」生成时，事后推断拿不到第二概念（原项目急诊 A2+ 仅 4.9%）。要真正达标必须让 Agent 2 出题时就填 `concepts[]`（见 §3 HC-27），**不要在事后硬造边**。
- **`[[K-M01-001]]` 指向主资料的 `####` 标题必为死链**：K-ID 是同一篇 MD 里的标题，不是独立笔记。要图谱节点与反链，必须生成实体笔记（见 §4）。

---

## 2. 数据契约

`question_bank/concept_graph.json`：

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-10-27T22:00:00",
  "subjects": [
    { "subject": "急诊", "batch": "batch043",
      "module_weights": {"M01": 8},
      "stats": {"nodes": 48, "questions": 200, "multi_label_rate": 0.049} }
  ],
  "nodes": [
    { "kc_id": "急诊:K-M01-001", "display_id": "K-M01-001", "subject": "急诊",
      "module": "M01", "title": "急诊医学的定位与 EMSS",
      "keypoints": [1], "source_pages": [1, 2],
      "status": "active", "weight": 4, "hub": 6, "prereq": ["急诊:K-M00-000"] }
  ],
  "edges": {
    "measures": [{ "qid": "batch043-M01-A1-005", "kc_id": "急诊:K-M01-001",
                   "role": "primary", "evidence": "题干命中：EMSS", "confidence": "high" }],
    "prereq":   [{ "from": "急诊:K-M01-001", "to": "急诊:K-M01-002",
                   "basis": "page_order", "evidence": "P1-2 → P2" }],
    "ref":      [{ "from": "急诊:K-M01-001", "to": "急诊:K-M01-004",
                   "basis": "same_keypoint", "evidence": "共享教师重点第1条" }],
    "module_prereq": [{ "from": "M01", "to": "M02", "basis": "module_order" }]
  }
}
```

配套产出：`question_bank/concept_labels.jsonl`（一题一行，带 evidence）、`question_bank/concept_prereq_overrides.json`（人工加/删边，写明理由）、`reports/validate/concept_graph_build|check*.json|md`。

---

## 3. HC-27 生成期概念标注（schema 2.1 · 2026-10-27 起）

> **驱动**：事后推断在「一题一锚点」题库上封顶 5%。多标签必须在出题时就给。

- **契约**：`schemas/agent2_output.schema.json` 的 `schema_version` 取 `1.0 / 2.0 / 2.1`；**2.1 起 `concepts` 为必填**，A2/A3/A4/X 至少 2 条。1.0/2.0 为历史产物，不追溯。
- **字段**：`concepts: [{role, keypoint, title, evidence}]`
  - `role`：`primary`（每题恰好 1 条）/ `differential`（干扰项对应的鉴别概念）/ `related`；
  - `keypoint`：教师重点条号（如「第2条」），**primary 必须等于本题 `keypoint_ref`**；
  - `title`：概念名，尽量用教师重点原文的词；
  - `evidence`：≥8 字，指出题干/选项/解析中的具体线索，不得只写「相关」。
- **门禁**：`python {SKILL}/scripts/check_source_concepts.py --file <题库 JSON> --batch {batchID}`
  - S1–S6：`concepts` 存在 / primary 唯一 / A2+ ≥2 条 / 字段长度 / primary 锚点一致 / 标题去重；
  - `--min-batch 44` 起强制，旧批次返回 **SKIP（退出码 2）**——SKIP 不等于 PASS。
- **标注优先级**：`label_concepts.py` 有源标注时走 `label_from_source`（keypoint 共属 → 标题重叠 → 标题回退，`source=declared`）；无源标注才推断（`source=inferred`）。解析不到的写入 `unresolved` 人工队列，**不静默丢弃**。

---

## 4. 工作流与命令

顺序固定，任一步 FAIL 就停在该步修数据：

```bash
# 1) 建图（必须最先；自动从 display_id 修模块 + 建页序/module_prereq 边）
python {SKILL}/scripts/build_concept_graph.py --out question_bank/concept_graph.json

# 2) 概念标注（有源标注走 declared，无则 inferred；也可先跑，再回到 1）
python {SKILL}/scripts/label_concepts.py --subject {科目}
python {SKILL}/scripts/build_concept_graph.py --labels

# 3) 门禁 C1–C8
python {SKILL}/scripts/check_concept_graph.py --subject {科目}

# 4) 概念卡（Obsidian 实体笔记 + 索引页 + MOC 回链）
python {SKILL}/scripts/build_concept_cards.py --subject {科目全称}
```

### 4.1 门禁口径（C1–C8）

| 检查 | 阈值 | FAIL 后果 |
|---|---|---|
| C1 无环 | 卡级 + 模块级拓扑排序成功 | 阻断 |
| C2 孤立节点 | 0（无 measures 且无 prereq） | 阻断 |
| C3 每题有主概念 | 未映射 >2% FAIL / >0 WARN | 阻断 |
| C4 多标签率（A2+） | 源标注批次 ≥98% 解析成功；推断批次 0 = FAIL、0–60% = WARN | 告警 |
| C5 边证据完整 | `evidence` 非空率 100% | 阻断 |
| C6 自环/重复边 | 0 | 阻断 |
| C7 无题卡 | WARN（提示改 `status` 或补题） | 告警 |
| C8 源标注解析完整性 | 报未解析条目 | 告警 |

`--strict` 让 WARN 也以非零码退出（CI 用）。单科约 0.4 秒，不拖慢 R2。

### 4.2 概念卡命名铁律

- 目录带**学科全称**、文件名带**学科前缀**：`Obsidian产物/概念卡/{学科全称}/{学科}-K-Mxx-xxx.md`。
  K-ID 在不同学科会重复（都叫 `K-M01-001`），裸名会造成 Obsidian 同名歧义。
- 索引页：`Obsidian产物/概念索引/{学科全称}_概念卡索引.md`（K-ID｜标题｜模块｜题数｜前置）。
- 回链：在学科 MOC 末尾加「🧠 概念卡（N）」区块。
- 卡片是**索引卡**，不复制正文；核心一句取卡片 `💡 记忆钩子` 行。

---

## 5. 本期不做（避免范围蔓延）

1. 押题卷概念映射——押题卷题目常无模块、无 KC、无锚点，硬匹配等于编造；
2. 无 KC 注册表的学科——需先跑一遍出题批次才能建；
3. DINA/DINO 参数估计——样本量不足，参数不可识别；
4. FSRS 权重优化——需 ≥1,000 次真实复习记录（`spaced_schedule.py` 先用固定间隔）；
5. 把主复习资料拆成「一句一卡」——破坏叙事链与锚点体系。
