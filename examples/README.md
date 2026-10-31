# 最小可运行示例

本目录与 `skills/medagentwork/assets/example_workspace/` 内容一致，只演示最小输入与 3 道示例题，不包含任何真实学校资料、教材或真题。

```text
minimal/
├── 输入素材/
│   └── 示例科目/
│       ├── 示例科目_教师重点_示例.md
│       └── 教材摘录.md
└── 中间产物/
    └── batch001/
        └── ALL_questions.json      # 3 道已通过 R1-R13 的示例题
```

## 推荐用法：一键创建可运行工作区

```bash
python {SKILL}/scripts/init_workspace.py ./我的医学复习 --subject <科目> --example
python {SKILL}/scripts/doctor.py --workspace ./我的医学复习
```

`--example` 会把上述示例复制到 `输入素材/<科目>/`（未给 `--subject` 时用 `示例科目`）、登记 `batch001`，并生成 `示例运行说明.md`。随后可直接运行：

```bash
cd ./我的医学复习
python {SKILL}/scripts/validate_options.py --batch batch001 --mode full
python {SKILL}/scripts/qbank.py export-md --file 中间产物/batch001/ALL_questions.json --out 中间产物/batch001/示例题库.md --title "示例科目·示例题库"
```

## 换成自己的资料

把 `输入素材/示例科目/` 换成你的科目目录，教师重点建议命名为：

```text
输入素材/<科目>/<科目>_教师重点_<学校或日期>.md
```

门禁命令按实际文件名读取，脚本不会展开 `*` 通配符。换一所学校时只需更换输入重点，题库、复习资料和质量门禁流程都不需要改。
