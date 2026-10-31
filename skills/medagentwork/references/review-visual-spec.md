# 复习资料视觉与排版规范（单一事实来源）

> 适用范围：教师重点蓝图版（BPA v1.0）、教学计划版、课程安排版等所有**复习资料**。
> 性质：视觉/排版口径的**最高优先级**文件；与 `bpa-v1.md`、`review-detail.md`、
> `Agent5_MedReview_Prompt.md` 冲突时，以本文件为准。
> 交付面：**仅 Markdown**。最终视觉呈现由 Obsidian 主题 / 打印导出决定；本规范不改变
> “交付只出 MD”的产物契约。

## 0. 先裁决三个历史冲突

| 争议项 | 最终裁决 | 落地要求 |
|---|---|---|
| `<details>/<summary>` 折叠区 | **禁用**。统一用 `#### 🔬 展开：{名称}`，内容默认可见 | 交付 MD 中 `<details` / `<summary` 计数必须为 0；`check_review_visual.py` 直接判 FAIL |
| 复习资料 HTML | **不是交付物**。`render_review.py` 仅历史遗留，不参与管线、不参与门禁、不作为验收对象 | 不生成、不引用、不要求 HTML；需要 PDF 时由用户从 Obsidian 人工导出 |
| Mermaid 图 | **禁用**。因果链、决策树、谱系图一律用 ASCII 图放在 ``` 代码块内 | 出现 ```mermaid 代码块即 FAIL |
| `**`/`*` 行内强调 | **禁用**。粗体 `<b>…</b>`、斜体 `<i>…</i>`，且必须成对 | `**` 计数非 0 或标签不配对即 FAIL |
| 视觉封面 | BPA 的“封面”是**内容封面**（权重/题型/卡片数/谱系位置/三个题眼/阅读时长），不是装饰性图形封面 | 不要求配图、不要求设计封面图；禁止为“好看”删减内容 |

## 1. 设计原则

1. **阅读路径优先**：先总览、再展开；保留 30 秒 / 3 分钟 / 30 分钟三条入口。
2. **层级靠文字也靠颜色**：`🔴 掌握` / `🟡 熟悉` / `🟢 了解` 必须同时有颜色标记和文字等级，不得只靠颜色传递信息。
3. **视觉呼吸**：每 3–5 行正文出现一个断点（Callout / 表格 / 展开区 / ASCII 图 / 分隔线）；全文不得出现连续 10 行纯文本。
4. **结构稳定**：同一册内模块与卡片结构一致，禁止“模板漂移”（同一册三种标题体例）。
5. **克制装饰**：单栏阅读、清晰标题层级、无花哨背景；不使用装饰性插图替代知识结构。
6. **内容优先**：好看可以加分，但不能为了排版删掉关键条件、数值、时间窗或鉴别轴。

## 2. 设计 Token

### 2.1 语义色（浅色）

| Token | 值 | 用途 |
|---|---|---|
| `--maw-text-primary` | `#1A1A2E` | 正文主色 |
| `--maw-text-secondary` | `#4A5568` | 次级说明 |
| `--maw-text-tertiary` | `#718096` | 页码、脚注、元信息 |
| `--maw-bg-primary` | `#FAFBFC` | 页面底色 |
| `--maw-bg-secondary` | `#FFFFFF` | 卡片/正文块 |
| `--maw-bg-callout` | `#F8F9FB` | Callout 底色 |
| `--maw-border` | `#E2E8F0` | 常规边框 |
| `--maw-master` | `#DC2626` | 🔴 掌握级 |
| `--maw-master-bg` | `#FEF2F2` | 掌握级浅底 |
| `--maw-master-border` | `#FECACA` | 掌握级边框 |
| `--maw-familiar` | `#D97706` | 🟡 熟悉级 |
| `--maw-familiar-bg` | `#FFFBEB` | 熟悉级浅底 |
| `--maw-familiar-border` | `#FDE68A` | 熟悉级边框 |
| `--maw-understand` | `#059669` | 🟢 了解级 |
| `--maw-understand-bg` | `#ECFDF5` | 了解级浅底 |
| `--maw-understand-border` | `#A7F3D0` | 了解级边框 |
| `--maw-warning` | `#D97706` | WARNING Callout |
| `--maw-tip` | `#7C3AED` | TIP Callout |
| `--maw-info` | `#2563EB` | INFO Callout |
| `--maw-success` | `#059669` | SUCCESS Callout |
| `--maw-accent` | `#2563EB` | 链接/强调/选中 |

### 2.2 语义色（深色）

| Token | 值 |
|---|---|
| `--maw-bg-primary` | `#0F1117` |
| `--maw-bg-secondary` | `#161822` |
| `--maw-bg-callout` | `#1A1C2A` |
| `--maw-text-primary` | `#E2E4E9` |
| `--maw-text-secondary` | `#A0A6B5` |
| `--maw-text-tertiary` | `#6B7280` |
| `--maw-border` | `#2A2D3A` |
| `--maw-master-bg` | `#3B1219` |
| `--maw-master-border` | `#5C1F24` |
| `--maw-familiar-bg` | `#3B2F0A` |
| `--maw-familiar-border` | `#5C4A1A` |
| `--maw-understand-bg` | `#0A2E1F` |
| `--maw-understand-border` | `#1A4A30` |

> 这些值与 `render_review.py` 的历史 CSS 及押题卷模板保持同一语义；复习资料实际使用
> `assets/review-visual.css` 作为 Obsidian 基线，不依赖 `render_review.py`。

## 3. 字体与字号

| 层级 | 字号 | 字重 | 行高 | 说明 |
|---|---:|---:|---:|---|
| H1 科目标题 | 28px | 800 | 1.25 | 一册只出现一次 |
| H2 模块标题 | 22px | 700 | 1.35 | `## 模块N：…` |
| H3 区块标题 | 18px | 600 | 1.45 | 前置/摘要/对比/因果/决策/一页纸 |
| H4 考点卡标题 | 16px | 600 | 1.5 | `#### 🔴 K-M…` / `#### 🔬 展开` |
| 正文 | 15px | 400 | 1.8 | 中文单行 28–35 字为宜，不超过 40 字 |
| 表格 | 13–14px | 400 | 1.6 | 单元格 ≤20 字 |
| 注释/页码 | 12px | 400 | 1.5 | 页码、来源、脚注 |

字体栈（HTML/Obsidian 基线）：

```text
-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei",
"Hiragino Sans GB", "WenQuanYi Micro Hei", sans-serif
```

等宽字体：`"SF Mono", "Cascadia Code", "Fira Code", "Consolas", monospace`。

内容宽度：网页/打印单栏 **720–780px**；Obsidian 阅读视图建议 `max-width: 760px`；不设双栏。
行高：正文 `1.8`；标题 `1.25–1.5`。

## 4. 版式结构

### 4.1 科目层（≤2 页）

- 使用指南 + 图例（🔴🟡🟢、卡片 ID 规则）。
- 科目蓝图：模块 × 权重 × 卡片 × 题型（一张表）。
- 三条阅读路径：30 秒 / 3 分钟 / 30 分钟。
- 五个记忆主轴、十个高频陷阱（每条 ≤1 行）。
- 疾病谱系总览 + 跨模块概念地图（各 1 张 ASCII 图）。

### 4.2 模块层（每模块 1+7，顺序固定）

1. 模块封面（内容封面）：权重｜题型｜卡片数｜谱系位置｜三个题眼｜阅读时长。
2. `🧩 前置知识检查`（3–5 问）。
3. `🎯 30 秒摘要`（5 条，每条 ≤30 字）。
4. `📋 考点卡`（九槽位，见 §5）。
5. `📊 对比速查`（2–4 张表，每表 3–5 列，首列是鉴别轴）。
6. `🔗 因果链`（1 张，5–9 节点，箭头标因果）。
7. `🌳 决策树`（1 棵，首分支=关键鉴别轴，每层 ≤3 分支）。
8. `📌 一页纸`（6 格：3 必考 + 2 易混 + 1 红线）+ `🔄 主动回忆`（8–12 题）。

### 4.3 卡片解剖

```text
#### 🔴 K-M{nn}-{nnn}｜{考点名}（教师重点第X条｜P###）

📌 重点原文（第X条）：{逐字照录}

<b>🎯 定位</b>：{一句话题眼 + 定义/解剖位置/分类}
<b>🧬 机制</b>：{正常→触发→病理→表现}
<b>👁 识别</b>：{典型场景 + 核心症状 + 关键体征 + 关键阴性}
<b>🔍 诊断</b>：{首选检查 + 确诊金标准 + 分级/分期界值}
<b>🩺 处置</b>：{治疗原则 + 一线方案 + 禁忌/转诊/随访}
<b>⚖️ 鉴别</b>：{≥3 行对比表，≥2 个鉴别对象}
<b>🚨 易错</b>：{1–2 个真实错误 + 正确口径}
<b>🧠 记忆钩子</b>：{一句话/口诀/对比锚}
<b>🔄 自测</b>：{2–3 个原子问题；答案进附录}
```

掌握级另加 `<b>🏥 案例</b>`（3–5 行病例 → 关键发现 → 最可能诊断 → 下一步）。

### 4.4 表格与图示

| 元素 | 规则 |
|---|---|
| 对比表 | 2–4 张/模块；首列是鉴别轴；每格 ≤20 字；最多 5 列 |
| 因果链 | 1 张/模块；5–9 节点；箭头表示因果；ASCII 代码块 |
| 决策树 | 1 棵/模块；首分支=关键鉴别轴；每层 ≤3 分支；ASCII 代码块 |
| 一页纸 | 1 张/模块；6 格：3 必考 + 2 易混 + 1 红线 |
| 表格宽度 | 不超过正文宽度；不出现超宽横表 |
| 图片 | 不强制；禁止用装饰图替代知识结构；复习资料不生成插图 |

### 4.5 Callout 与视觉呼吸

- 5 种类型：`WARNING` / `TIP` / `INFO` / `SUCCESS` / `NOTE`。
- 每模块至少 **4 个 Callout**，至少使用 **4 种**类型。
- D1 第一性原理段结束必须接 Callout 或 `#### 🔬 展开：`。
- D2 因果链图下方必须接 `> [!INFO]` 解释临床含义。
- 每 3–5 行正文出现一个断点；不得连续 10 行纯文本。
- Callout 标题 ≤20 字；不堆叠多个 Callout。

### 4.6 展开区

- 统一格式：`#### 🔬 展开：{名称}`。
- 每模块 ≥2 个展开区。
- 内容默认可见；禁止 `<details>`/`<summary>`、禁止折叠后隐藏关键条件。

## 5. 颜色与无障碍

1. **颜色不是唯一通道**：🔴🟡🟢 必须同时有“掌握/熟悉/了解”文字标签；Callout 必须有标题文字。
2. **对比度**：正文与背景 ≥4.5:1；大字号标题 ≥3:1；语义色在浅底/深底上均需达到 4.5:1。
3. **不依赖红绿区分**：不要只用红/绿表示对错；配合 ✓/✗、文字或图标。
4. **深色模式**：使用 §2.2 的深色 token；不要简单反转色相。
5. **可读性**：不使用花哨背景、渐变大面积铺底、低对比装饰字。

## 6. Markdown 与导出契约

### 6.1 允许

- `h1`–`h6`、空行分段、标准 Markdown 表格、``` 代码块、`---` 分隔线、列表。
- 行内 `<b>粗</b>`、`<i>斜</i>`、`` `代码` ``。
- Obsidian Callout：`> [!WARNING|TIP|INFO|SUCCESS|NOTE] 标题`（连续 `>` 行成卡）。
- 展开区：`#### 🔬 展开：{名称}`。

### 6.2 禁止

- ❌ Mermaid（一律 ASCII 图）。
- ❌ `<details>` / `<summary>`。
- ❌ `**` / `*` 行内强调。
- ❌ 其它 HTML 标签（`<b>` / `<i>` 除外）。
- ❌ YAML front matter、任务列表 `- [ ]`。
- ❌ 流程残留：`## 📦 复习资料批次 X/Y`、`✅ 批次完成`、`V1-V14 视觉质量自检报告` 等。
- ❌ 用装饰图替代关键条件、数值、时间窗或鉴别轴。

### 6.3 PDF

- PDF **一律人工导出**；管线与脚本不生成、不引用 PDF 路径。
- 推荐从 Obsidian 导出，启用 `assets/review-visual.css`；打印前检查分页、表格宽度、Callout 是否被截断。

## 7. Obsidian / 打印实施

1. 将 `assets/review-visual.css` 复制到 Obsidian vault 的 `.obsidian/snippets/`。
2. 在“设置 → 外观 → CSS 片段”启用 `review-visual`。
3. 打印/PDF 使用 Obsidian 导出；CSS 内含 `@media print` 基线（A4、页边距、避免卡片/表格跨页断裂）。
4. 主题可能覆盖片段；以实际阅读视图为准，必要时在片段末尾追加 `!important` 前先确认影响范围。
5. 该 CSS 是**可选基线**，不作为交付物；交付物仍是 MD。

## 8. 视觉质量门禁

### 8.1 自动检查（`check_review_visual.py`）

| 规则 | 检查内容 | 阈值来源 |
|---|---|---|
| V1 三色覆盖 | `####` 卡片标题中带 🔴🟡🟢 的比例 | `visual_tier_coverage_min` |
| V2 Callout | 每模块 Callout 数、类型数 | `visual_callout_density_min` / `visual_callout_types_min` |
| V3 视觉呼吸 | 连续纯文本行数 | `visual_plain_text_run_max` |
| V4 展开区 | 每模块 `#### 🔬 展开` 数；`<details>` 计数 | `visual_expand_density_min` |
| V5 表格 | 每模块表格块数 | `visual_tables_per_module_min` |
| V14 导出兼容 | `**`、Mermaid、`<details>`、`<b>/<i>` 配对；单 `*`/孤立 `*` 由人工抽检 | 硬规则 + 人工 |

> 教学计划版若没有 `####` 卡片标题，V1 记为 SKIP（不视为 PASS），按 🔴🟡🟢 文字等级人工抽检。

### 8.2 既有门禁

| 规则 | 由谁检查 |
|---|---|
| V6 术语附录 ≥20 | `check_review_detail.py` |
| V7 页码附录真实页码 | `check_review_detail.py` + `verify_page_numbers.py` |
| V8 填空答案《》 | 人工抽检（当前无机械检查） |
| V9–V13 深度五维 | `check_review_detail.py` 的部分槽位 + 人工抽检 |
| V17 教师重点覆盖 | `check_keypoint_coverage.py` |
| V18 详细度 | `check_review_detail.py` |

### 8.3 人工验收

- **3-10-30**：每模块抽 3 张卡遮住正文只读锚点；每科抽 10 个数字回教材；30 秒盲读一页纸能否复述 4/5 个必考点。
- 在 Obsidian 实际打开：检查标题层级、Callout、表格宽度、展开区、深色模式、打印分页。
- 颜色检查：遮住颜色只看文字标签，仍能区分掌握/熟悉/了解。

## 9. 与其它文档的关系

| 文档 | 关系 |
|---|---|
| `bpa-v1.md` | BPA 的结构/卡片/装置规则；视觉口径以本文件为准 |
| `review-detail.md` | 九槽位/模块八块/详细度阈值；本文件补视觉与排版约束 |
| `Agent5_MedReview_Prompt.md` | 生成提示词；V1–V14 自检以本文件为准 |
| `quality-gate.md` | R2/R3 的 `review_visual` 检查由 `check_review_visual.py` 执行 |
| `assets/review-visual.css` | 可选 Obsidian/打印基线；不是交付物 |

## 10. 变更管理

- 本文件是视觉规范的**单一事实来源**；修改 token、字号、阈值、允许/禁止语法时必须同步：
  `quality_policy.json` 的 `visual_*` 阈值、`check_review_visual.py`、`assets/review-visual.css`、`Agent5_MedReview_Prompt.md` 的 V1–V14。
- 旧批次不追溯；新批次/新版本按本规范执行。
- 若未来恢复 HTML 交付，必须先在本文件增加“HTML 交付面”章节、明确模板与验收标准，再改 `SKILL.md` 与门禁；不得先产出 HTML 再补规范。
