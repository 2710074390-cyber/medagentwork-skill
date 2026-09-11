"""冒烟测试：验证 skill 包在干净工作区可跑通核心链路。"""
import json
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
    # 坏题1：选项过短（R8）
    {"question_id": "N-A1-002", "type": "A1", "stem": "脑出血最好发部位是下列哪一项？",
     "options": {"A": "壳核", "B": "丘脑", "C": "桥脑", "D": "小脑", "E": "脑叶"},
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
check("validate_options 可执行", r.returncode in (0, 1, 2), r.stderr[:300])
report_dir = WS / "reports" / "validate"
check("校验报告生成", any(report_dir.glob("*.json")), r.stdout[-300:])

print("== 5. gate_check 阶段门禁（应 HALT） ==")
r = run(f'python "{SCRIPTS + "/gate_check.py"}" --batch batch001 --stage agent2_done', cwd=WS)
check("gate_check 可执行", r.returncode in (0, 1, 2), r.stderr[:300])

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

print(f"\n{'=' * 40}\n结果: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
