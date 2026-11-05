"""冒烟测试：验证 skill 包在干净工作区可跑通核心链路。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "medagentwork"
SCRIPTS = (SKILL / "scripts").as_posix()
WS = Path(__file__).resolve().parent / "test_ws"

PASS = 0
FAIL = 0


def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ── 准备干净工作区 ──
if WS.exists():
    shutil.rmtree(WS)
(WS / "输入素材" / "神经病学").mkdir(parents=True)
(WS / "中间产物" / "batch001").mkdir(parents=True)
(WS / "输入素材" / "神经病学" / "第1章.md").write_text(
    "# 第1章 脑血管疾病\n脑卒中分为缺血性和出血性两大类。", encoding="utf-8")

print("== 1. 初始化状态文件 ==")
r = run(f'python -c "import sys; sys.path.insert(0, \'{SCRIPTS}\'); '
        f'import workflow_state as ws; ws.save_state({{\'schema_version\': 2}})"', cwd=WS)
check("workflow_state.json 创建", (WS / "workflow_state.json").exists(), r.stderr[:200])

print("== 2. 登记批次 (ensure_batch + save_state) ==")
r = run(f'python -c "import sys; sys.path.insert(0, \'{SCRIPTS}\'); '
        f'import workflow_state as ws; s, err = ws.load_state(); '
        f'b, c = ws.ensure_batch(s, \'batch001\'); b.update(subject=\'脑血管疾病\', target=10); '
        f'ws.save_state(s); print(b[\'batch_id\'], \'created=\' + str(c))"', cwd=WS)
check("批次登记写盘", "batch001" in r.stdout and "created" in r.stdout, r.stdout + r.stderr[:300])

print("== 3. 写入测试题库（1 好 + 2 坏） ==")
questions = [
    {"question_id": "N-A1-001", "type": "A1", "stem": "缺血性脑卒中最常见的病因是下列哪一项？",
     "options": {"A": "大动脉粥样硬化性血栓形成所致", "B": "脑动静脉畸形血管破裂所致",
                 "C": "淀粉样脑血管病出血所致", "D": "蛛网膜下腔动脉瘤破裂",
                 "E": "脑静脉窦血栓形成所致"},
     "answer": "A", "analysis": "缺血性脑卒中以大动脉粥样硬化性血栓形成最常见。",
     "module": "M1", "bloom_level": "记忆"},
    # 坏题1：含禁止项"以上都是"（R1 FAIL）+ 其余选项过短（R8 WARN）
    {"question_id": "N-A1-002", "type": "A1", "stem": "脑出血最好发部位是下列哪一项？",
     "options": {"A": "以上都是", "B": "丘脑", "C": "桥脑", "D": "小脑", "E": "脑叶"},
     "answer": "A", "analysis": "基底节区壳核出血最常见。",
     "module": "M1", "bloom_level": "记忆"},
    # 坏题2：无解析
    {"question_id": "N-A1-003", "type": "A1", "stem": "蛛网膜下腔出血首选的检查是？",
     "options": {"A": "头颅CT平扫", "B": "头颅MRI平扫", "C": "脑电图检查", "D": "经颅多普勒", "E": "腰穿脑脊液"},
     "answer": "A",
     "module": "M1", "bloom_level": "理解"},
]
(WS / "中间产物" / "batch001" / "ALL_questions.json").write_text(
    json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

print("== 4. GATE-A2 校验（应 FAIL>0 并 BLOCK） ==")
r = run(f'python "{SCRIPTS + "/validate_options.py"}" --batch batch001 --mode full', cwd=WS)
check("FAIL>0 时退出码 1", r.returncode == 1, f"returncode={r.returncode}; {r.stderr[:200]}")
report_dir = WS / "reports" / "validate"
check("校验报告生成", any(report_dir.glob("*.json")), r.stdout[-300:])

print("== 5. gate_check 阶段门禁（应 HALT） ==")
r = run(f'python "{SCRIPTS + "/gate_check.py"}" --batch batch001 --stage agent2_done', cwd=WS)
check("GATE-A2 在 FAIL>0 时 BLOCKED（exit 1）", r.returncode == 1,
      f"returncode={r.returncode}; {r.stdout[-300:]}{r.stderr[:200]}")

print("== 6. Bloom 采样 ==")
r = run(f'python "{SCRIPTS + "/bloom_sampler.py"}" --batch batch001 --threshold 15', cwd=WS)
check("bloom_sampler 可执行", r.returncode in (0, 1, 2), r.stderr[:300])

print("== 7. 契约检查 ==")
r = run(f'python "{SCRIPTS + "/contract_check.py"}" --batch batch001', cwd=WS)
check("contract_check 可执行", r.returncode in (0, 1, 2), r.stderr[:300])

print("== 8. workflow_state CLI ==")
r = run(f'python "{SCRIPTS + "/workflow_state.py"}" --show batch001', cwd=WS)
check("workflow_state CLI 可执行", r.returncode == 0, r.stderr[:300])

print("== 9. 修复后重跑（修复坏题 → 应 FAIL==0 放行） ==")
questions[1]["options"] = {"A": "基底节区壳核（大脑中动脉深穿支）", "B": "丘脑（大脑后动脉深穿支）",
                            "C": "脑桥（基底动脉旁正中支）", "D": "小脑（小脑上动脉）", "E": "脑叶（皮质下白质）"}
questions[2]["analysis"] = "蛛网膜下腔出血首选头颅 CT 平扫，敏感性高且快速。"
(WS / "中间产物" / "batch001" / "ALL_questions.json").write_text(
    json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
r2 = run(f'python "{SCRIPTS + "/validate_options.py"}" --batch batch001 --mode full', cwd=WS)
summary_files = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
latest = json.loads(summary_files[-1].read_text(encoding="utf-8"))
fails = latest.get("summary", {}).get("fail", 0) if isinstance(latest, dict) else None
check("修复后 FAIL==0", fails == 0, f"summary.fail={fails}; stdout尾部: {r2.stdout[-200:]}")
check("仅 WARN 时退出码 0", r2.returncode == 0, f"returncode={r2.returncode}")

print("== 10. MD 导出（qbank.py） ==")
r = run(f'python "{SCRIPTS + "/qbank.py"}" export-md --file 中间产物/batch001/ALL_questions.json '
        f'--out 中间产物/batch001/test_export.md --title "神经病学·冒烟测试"', cwd=WS)
check("export-md 生成", (WS / "中间产物" / "batch001" / "test_export.md").exists(),
      r.stdout[-200:] + r.stderr[:200])

print("== 11. 规则命中断言（评审 §七.5：不能只验'可执行'，要验'规则真的命中'） ==")
# 每个探针题都构造成必然触发一条特定规则；断言该 rule 出现在校验报告里。
# 若某条规则被改坏/失效（如 R1 死代码那类问题），本步会直接失败。
rule_probe = [
    {"question_id": "P-R1", "type": "A1", "stem": "关于该病，下列说法正确的是？",
     "options": {"A": "以上都是", "B": "选项B内容", "C": "选项C内容", "D": "选项D内容", "E": "选项E内容"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R1W", "type": "A1", "stem": "该病的病理分型是？",
     "options": {"A": "腺癌", "B": "鳞癌（常见类型）", "C": "小细胞癌", "D": "大细胞癌", "E": "类癌"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R2", "type": "A1", "stem": "该病最常见的病因是下列哪一项？",
     "options": {"A": "由多种遗传与环境因素长期共同作用导致的复杂病理生理过程",
                 "B": "感染", "C": "外伤", "D": "肿瘤", "E": "免疫"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R5", "type": "A1", "stem": "下列哪项检查最有价值？",
     "options": {"A": "CT", "B": "MRI", "C": "超声", "D": "X线"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "理解"},
    {"question_id": "P-R7", "type": "A1", "stem": "该病的典型表现是？",
     "options": {"A": "发热", "B": "咳嗽咳痰气促..", "C": "胸痛", "D": "咯血", "E": "盗汗"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R8", "type": "A1", "stem": "该病最常累及的器官是？",
     "options": {"A": "肾脏", "B": "肝脏和脾脏的", "C": "心脏", "D": "肺脏", "E": "脑"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R10", "type": "A1",
     "stem": "患者突发胸骨后压榨性疼痛伴心肌梗死典型心电图改变，最可能的诊断是？",
     "options": {"A": "急性心肌梗死", "B": "主动脉夹层", "C": "肺栓塞", "D": "心包炎", "E": "气胸"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "分析"},
    {"question_id": "P-R11", "type": "A1",
     "stem": "患者因慢性阻塞性肺疾病急性加重出现呼吸衰竭，血气分析示低氧血症，最合适的处理是？",
     "options": {"A": "急性加重", "B": "慢性阻塞性肺疾病患者需呼吸衰竭处理",
                 "C": "低氧血症", "D": "血气分析", "E": "肺疾病"},
     "answer": "B", "analysis": "解析内容解析内容", "bloom_level": "应用"},
    {"question_id": "P-R12", "type": "A1", "stem": "该病的病理分型是？",
     "options": {"A": "腺癌", "B": "鳞癌（见上文）", "C": "小细胞癌", "D": "大细胞癌", "E": "类癌"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-R13", "type": "A1", "stem": "该病最常见的转移途径是？",
     "options": {"A": "淋巴道转移", "B": "血道转移", "C": "种植转移",
                 "D": "直接蔓延至邻近组织器官并沿自然腔道播散", "E": "混合转移"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
    {"question_id": "P-JS1", "type": "A1", "stem": "该病诊断依据...",
     "options": {"A": "症状", "B": "体征", "C": "实验室检查", "D": "影像学", "E": "病理"},
     "answer": "A", "analysis": "解析内容解析内容", "bloom_level": "记忆"},
]
probe_path = WS / "中间产物" / "batch001" / "_rule_probe.json"
probe_path.write_text(json.dumps(rule_probe, ensure_ascii=False, indent=2), encoding="utf-8")
r = run(f'python "{SCRIPTS + "/validate_options.py"}" --file 中间产物/batch001/_rule_probe.json --mode full', cwd=WS)
check("FAIL>0 时退出码 1", r.returncode == 1, f"returncode={r.returncode}")
probe_report = WS / "reports" / "validate" / "validate_options_report__rule_probe.json"
hit_rules = set()
hit_details = []
if probe_report.exists():
    data = json.loads(probe_report.read_text(encoding="utf-8"))
    for issue in data.get("issues", []):
        hit_rules.add(issue.get("rule"))
        hit_details.append(f"[{issue.get('rule')}] {issue.get('detail')}")

# R1~R13 + JS1 逐条断言（R11 依赖关键词抽取，已在探针中构造确定性命中）
for rule in ["R1", "R2", "R5", "R7", "R8", "R10", "R11", "R12", "R13", "JS1"]:
    check(f"规则 {rule} 命中", rule in hit_rules,
          f"报告未包含 {rule}；实际命中={sorted(r for r in hit_rules if r)}")

# R1 死代码回归断言（评审 §6.5-P1.1）：末尾括号说明后缀必须能触发 R1 WARN
r1_warn_hit = any(d.startswith("[R1]") and "括号说明后缀" in d for d in hit_details)
check("R1 末尾括号后缀分支可达（死代码回归）", r1_warn_hit,
      "R1 的括号后缀 WARN 分支未触发 —— 可能又变回不可达分支")

# R2 文案与实现一致性断言（评审 §6.5-P1.4）：取的是 min 而非均值，文案应为"最短"
r2_warn = [d for d in hit_details if d.startswith("[R2]") and "显著长于" in d]
if r2_warn:
    check("R2 文案用'最短'而非'均'", all("最短" in d for d in r2_warn),
          f"R2 文案与实现不符: {r2_warn}")
else:
    check("R2 文案用'最短'而非'均'", True, "（本次未产生 R2 WARN，跳过）")

# R8 科目豁免来自配置而非硬编码（评审 §七.9）
r8_config_ok = run(f'python -c "import sys; sys.path.insert(0, \'{SCRIPTS}\'); '
                   f'from pipeline_config import get_r8_legit_terms as g; '
                   f'assert \'气\' in g(\'中医\'), \'中医词表未生效\'; '
                   f'assert \'妄想\' in g(), \'默认词表缺失\'; print(\'ok\')"', cwd=WS)
check("R8 豁免词表由 pipeline.yaml 驱动", "ok" in r8_config_ok.stdout,
      r8_config_ok.stdout + r8_config_ok.stderr[:200])

print("== 12. 首次使用：--example + doctor ==")
example_ws = WS / "_example_ws"
r = run(f'python "{SCRIPTS + "/init_workspace.py"}" "{example_ws}" --subject 示例科目 --example')
check("init_workspace --example 可执行", r.returncode == 0, r.stdout[-200:] + r.stderr[:200])
check("示例题库已复制", (example_ws / "中间产物" / "batch001" / "ALL_questions.json").exists(),
      r.stdout[-200:])
check("示例运行说明已生成", (example_ws / "示例运行说明.md").exists(), r.stdout[-200:])
r = run(f'python "{SCRIPTS + "/doctor.py"}" --workspace "{example_ws}"')
check("doctor 在示例工作区 exit 0", r.returncode == 0, r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS + "/validate_options.py"}" --batch batch001 --mode full', cwd=example_ws)
check("示例题库 validate exit 0", r.returncode == 0, r.stdout[-300:] + r.stderr[:200])

print("== 13. 复习资料视觉门禁（V1–V5 + V14） ==")
visual_valid = WS / "_visual_valid.md"
visual_valid.write_text("""# 示例复习资料

## 模块1：示例

#### 🔴 K-M01-001｜示例考点一

📌 重点原文（第1条）：示例原文。

<b>🎯 定位</b>：一句话题眼。
<b>🧬 机制</b>：正常到异常的因果。

> [!WARNING] 红线
> 示例红线。

> [!TIP] 记忆
> 示例口诀。

| 鉴别 | 甲 | 乙 |
|---|---|---|
| 关键轴 | 甲特征 | 乙特征 |

#### 🔬 展开：机制

> [!INFO] 图示说明
> 示例说明。

> [!NOTE] 补充
> 示例补充。

#### 🟡 K-M01-002｜示例考点二

<b>🎯 定位</b>：第二张卡。

| 鉴别 | 甲 | 乙 |
|---|---|---|
| 关键轴 | 甲特征 | 乙特征 |

#### 🔬 展开：鉴别

> [!SUCCESS] 结论
> 示例结论。
""", encoding="utf-8")
r = run(f'python "{SCRIPTS + "/check_review_visual.py"}" --md "{visual_valid}" '
        f'--profile release_teacher_keypoint --quiet')
check("视觉规范样例 PASS", r.returncode == 0, r.stdout[-300:] + r.stderr[:200])

visual_invalid = WS / "_visual_invalid.md"
visual_invalid.write_text("""# 示例复习资料

## 模块1：示例

#### 🔴 K-M01-001｜示例考点一

**禁止的 Markdown 粗体**

<details>
<summary>折叠区</summary>
折叠内容
</details>
""", encoding="utf-8")
r = run(f'python "{SCRIPTS + "/check_review_visual.py"}" --md "{visual_invalid}" '
        f'--profile release_teacher_keypoint --quiet')
check("视觉门禁拦截 details/**", r.returncode == 1, r.stdout[-300:] + r.stderr[:200])

print("== 14. 防跳过门禁：真实 gate_run 链路（a2→a3→a4→export）+ 审计 ==")
# 脚本按 cwd 定位工作区：本段所有命令都在测试工作区内执行（与真实用法一致）。
os.chdir(WS)
ledger_file = lambda b: WS / "最终产物" / b / "_gate_ledger.json"

# 14.1 夹具：登记 legacy 批次（非 strict）+ 造 Bloom 均衡题库 + A3 报告 + A4 产物/追溯日志
make_batch = WS / "_make_batch.py"
make_batch.write_text(f'''
import json, sys
from pathlib import Path
sys.path.insert(0, r"{SCRIPTS}")
import workflow_state as ws
import gate_check as gc

batch = sys.argv[1]
state, _ = ws.load_state()
if not isinstance(state, dict):
    state = {{"schema_version": 2}}
b, _ = ws.ensure_batch(state, batch)
b["subject"] = "示例科目"
b["evidence_binding_mode"] = "legacy"  # 非 strict：夹具无需完整证据绑定
ws.save_state(state)

src = Path(r"{Path(SCRIPTS).parent.as_posix()}") / "assets/example_workspace/中间产物/batch001/ALL_questions.json"
data = json.loads(src.read_text(encoding="utf-8"))
for q, lvl in zip(data, ("记忆", "理解", "应用")):
    q["bloom_level"] = lvl
mid = Path("中间产物") / batch / "ALL_questions.json"
mid.parent.mkdir(parents=True, exist_ok=True)
mid.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

dist, _ = gc.recompute_bloom_from_qbank(batch, mid)
qc = Path("质检报告") / batch / "A3_质检报告.json"
qc.parent.mkdir(parents=True, exist_ok=True)
qc.write_text(json.dumps({{
    "report_metadata": {{"gate_decision": "PASS", "batch": batch}},
    "gate_decision": "PASS",
    "dimensions": {{"D20": 10}},
    "bloom_distribution": {{"actual": dist}},
    "overall_score": 90,
}}, ensure_ascii=False, indent=2), encoding="utf-8")

fin = Path("最终产物") / batch / "ALL_questions_FIXED.json"
fin.parent.mkdir(parents=True, exist_ok=True)
fin.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
(Path("最终产物") / batch / "AGENT4_追溯日志.json").write_text(json.dumps({{
    "batch": batch, "source_file_synced": True, "patches": []
}}, ensure_ascii=False), encoding="utf-8")
print("fixture ready", batch)
''', encoding="utf-8")
r = run(f'python "{make_batch}" batch020')
check("夹具批次 batch020 就绪",
      r.returncode == 0 and (WS / "中间产物" / "batch020" / "ALL_questions.json").exists(),
      r.stdout[-300:] + r.stderr[:400])

# 14.2 缺上游回执 → 执行前 BLOCKED，且不写回执
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch020 --stage a4')
check("缺上游回执 → 执行前 BLOCKED", r.returncode == 1 and "BLOCKED" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])
check("BLOCKED 不写回执", not ledger_file("batch020").exists(), r.stdout[-200:])

# 14.3 真实跑 a2 → a3 → a4（回归：telemetry 签名崩溃 / 状态步骤机械补写）
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch020 --stage a2')
check("gate_run a2 真实 PASS 并写回执",
      r.returncode == 0 and ledger_file("batch020").exists(), r.stdout[-300:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch020 --stage a3')
check("gate_run a3 真实 PASS（telemetry 回归）", r.returncode == 0,
      r.stdout[-400:] + r.stderr[:400])
r = run(f'python "{SCRIPTS}/gate_ledger.py" verify --batch batch020 --stage a3')
check("a3 回执验真 PASS", r.returncode == 0 and "PASS" in r.stdout, r.stdout[-300:])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch020 --stage a4')
check("gate_run a4 真实 PASS 并写回执", r.returncode == 0,
      r.stdout[-400:] + r.stderr[:400])
telemetry_probe = (f'python -c "import sys; sys.path.insert(0, r\'{SCRIPTS}\'); '
                   "import telemetry; telemetry.log_gate_check('b','a3','PASS',reason='probe'); "
                   "print('ok')\"")
r = run(telemetry_probe)
check("telemetry.log_gate_check 接受 reason=（P0 回归）",
      r.returncode == 0 and "ok" in r.stdout, r.stdout[-300:] + r.stderr[:300])

# 14.4 交付口：A2/A3/A4 回执齐全 → 放行，并写 export 回执绑定 MD
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json')
check("有 A2/A3/A4 回执 → 交付放行", r.returncode == 0 and
      (WS / "最终产物" / "batch020" / "ALL_questions_FIXED.md").exists(),
      r.stdout[-300:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_ledger.py" verify --batch batch020 --stage export')
check("交付 MD 已写入 export 回执", r.returncode == 0 and "PASS" in r.stdout, r.stdout[-300:])
r = run(f'python "{SCRIPTS}/gate_audit.py" --batch batch020')
check("审计：完整链 PASS", r.returncode == 0 and "PASS" in r.stdout,
      r.stdout[-400:] + r.stderr[:300])

# 14.5 篡改 JSON → 字节绑定失效 → 交付拒收 + 审计 FAIL
fixed_path = WS / "最终产物" / "batch020" / "ALL_questions_FIXED.json"
original_bytes = fixed_path.read_bytes()
fixed_path.write_bytes(original_bytes + b"\n")
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json')
check("篡改 JSON → 交付被拒", r.returncode == 1 and "ARTIFACT_MISMATCH" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/gate_audit.py" --batch batch020')
check("审计：篡改 JSON FAIL", r.returncode == 1 and "ARTIFACT_MISMATCH" in r.stdout,
      r.stdout[-400:] + r.stderr[:200])
fixed_path.write_bytes(original_bytes)
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json')
check("还原 JSON 后交付恢复", r.returncode == 0, r.stdout[-300:] + r.stderr[:300])

# 14.6 篡改交付 MD → export 回执字节不符 → 审计 FAIL；重新导出恢复
md_path = WS / "最终产物" / "batch020" / "ALL_questions_FIXED.md"
md_path.write_text(md_path.read_text(encoding="utf-8") + "\n手改一行\n", encoding="utf-8")
r = run(f'python "{SCRIPTS}/gate_audit.py" --batch batch020')
check("审计：手改交付 MD FAIL", r.returncode == 1 and "ARTIFACT_MISMATCH" in r.stdout,
      r.stdout[-400:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json')
check("重新导出后交付恢复", r.returncode == 0, r.stdout[-300:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_audit.py" --batch batch020')
check("审计：重新导出后 PASS", r.returncode == 0 and "PASS" in r.stdout,
      r.stdout[-400:] + r.stderr[:200])

# 14.7 删回执链 → 交付拒收
ledger_backup = ledger_file("batch020").read_bytes()
ledger_file("batch020").unlink()
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json')
check("删回执 → 交付拒收", r.returncode == 1 and "LEDGER_MISSING" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])
ledger_file("batch020").write_bytes(ledger_backup)

# 14.8 插入伪造回执 → 断链检测
insert_helper = WS / "_insert_bad_stamp.py"
insert_helper.write_text(f'''
import sys
sys.path.insert(0, r"{SCRIPTS}")
import gate_ledger as gl
led, err = gl.load_ledger("batch020")
if err or led is None:
    raise SystemExit(err or "no ledger")
led["stamps"].append({{"seq": 99, "stage": "a4", "verdict": "PASS", "artifacts": []}})
gl.write_ledger(led)
print("inserted")
''', encoding="utf-8")
r = run(f'python "{insert_helper}"')
check("插入伪造回执", r.returncode == 0, r.stdout[-200:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_ledger.py" verify --batch batch020 --stage a4')
check("伪造回执 → 断链",
      r.returncode == 1 and ("CHAIN_BROKEN" in r.stdout or "SEQ_MISMATCH" in r.stdout),
      r.stdout[-300:] + r.stderr[:200])
ledger_file("batch020").write_bytes(ledger_backup)

# 14.9 dry-run 不写回执；跳过 a3 直接 a4 → BLOCKED
r = run(f'python "{make_batch}" batch021')
check("夹具批次 batch021 就绪", r.returncode == 0, r.stdout[-200:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch021 --stage a2 --dry-run')
check("dry-run 通过但不写回执", r.returncode == 0 and not ledger_file("batch021").exists(),
      r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch021 --stage a2')
check("batch021 a2 写回执", r.returncode == 0 and ledger_file("batch021").exists(),
      r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch021 --stage a4')
check("跳过 a3 直接 a4 → BLOCKED", r.returncode == 1 and "BLOCKED" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])

# 14.10 非 batchNNN 目录：交付口与审计都不放行（防「换名字让防护静默失效」）
bad_dir = WS / "最终产物" / "batch1"
bad_dir.mkdir(parents=True, exist_ok=True)
shutil.copy(WS / "最终产物" / "batch020" / "ALL_questions_FIXED.json",
            bad_dir / "ALL_questions_FIXED.json")
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch1/ALL_questions_FIXED.json')
check("非 batchNNN 目录 → 交付拒收", r.returncode == 1 and "BATCH_NAME_INVALID" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/gate_audit.py" --batch batch1')
check("非 batchNNN 目录 → 审计 FAIL", r.returncode == 1 and "BATCH_NAME_INVALID" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])

# 14.11 阶段适用性机械判定（纯题库批次跳过 a5；纯复习资料批次跳过 a2/a3/a4/lv）
review_only = WS / "_make_review_only.py"
review_only.write_text(f'''
import sys
sys.path.insert(0, r"{SCRIPTS}")
import workflow_state as ws
state, _ = ws.load_state()
if not isinstance(state, dict):
    state = {{"schema_version": 2}}
b, _ = ws.ensure_batch(state, "batch030")
b["subject"] = "示例科目"
b["product_types"] = ["review_material"]
ws.save_state(state)
print("ok")
''', encoding="utf-8")
r = run(f'python "{review_only}"')
check("复习资料批次登记", r.returncode == 0, r.stdout[-200:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch030 --stage a2')
check("纯复习资料批次：a2 机械判定 NOT_APPLICABLE",
      r.returncode == 0 and "NOT_APPLICABLE" in r.stdout and not ledger_file("batch030").exists(),
      r.stdout[-300:] + r.stderr[:200])
r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch021 --stage a5')
check("纯题库批次：a5 机械判定 NOT_APPLICABLE",
      r.returncode == 0 and "NOT_APPLICABLE" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])

# 14.12 输出路径含 ".."：交付口按解析后的真实落点判定（不能靠路径段骗过）
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch020/ALL_questions_FIXED.json '
        f'--out "最终产物/batch020/../../最终产物/batch1/ALL_questions_FIXED.md"')
check("输出路径含 .. → 按真实落点拒绝", r.returncode == 1 and "BATCH_NAME_INVALID" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])

# 14.13 schema 2.0+ 批次：缺 lv 回执 → 交付口拒绝
r = run(f'python "{make_batch}" batch022')
check("夹具批次 batch022 就绪", r.returncode == 0, r.stdout[-200:] + r.stderr[:300])
schema20 = WS / "_set_schema20.py"
schema20.write_text('''
import json
from pathlib import Path
for rel in ("中间产物/batch022/ALL_questions.json", "最终产物/batch022/ALL_questions_FIXED.json"):
    p = Path(rel)
    data = json.loads(p.read_text(encoding="utf-8"))
    for q in data:
        q["schema_version"] = "2.0"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("ok")
''', encoding="utf-8")
r = run(f'python "{schema20}"')
check("batch022 标为 schema 2.0", r.returncode == 0, r.stdout[-200:] + r.stderr[:300])
for stage in ("a2", "a3", "a4"):
    r = run(f'python "{SCRIPTS}/gate_run.py" --batch batch022 --stage {stage}')
    if r.returncode != 0:
        break
check("schema 2.0+ 批次 a2→a3→a4 写回执", r.returncode == 0,
      r.stdout[-400:] + r.stderr[:300])
r = run(f'python "{SCRIPTS}/qbank.py" export-md --file 最终产物/batch022/ALL_questions_FIXED.json')
check("schema 2.0+ 缺 lv → 交付拒收", r.returncode == 1 and "STAGE_MISSING" in r.stdout and "lv" in r.stdout,
      r.stdout[-300:] + r.stderr[:200])
print(f"\n{'=' * 40}\n结果: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
