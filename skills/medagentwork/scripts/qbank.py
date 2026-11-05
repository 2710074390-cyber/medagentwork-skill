#!/usr/bin/env python3
"""
qbank.py — MedAgentWork 统一题库数据层 v1.0 (2026-08-13 · 架构 P0-1)

解决的问题（实证: 7 个题库文件 6 种字段结构）:
  - 格式漂移: 每个下游脚本各自解析 6 种字段变体
  - 无跨批次去重: 没有机制防止同一题干在不同批次重复出现
  - 无统一查询/统计/导出入口

方案:
  - question_bank/registry.jsonl  ← 全库题目注册表（一行一题，仅元数据，不复制内容）
  - question_bank/registry_meta.json ← 注册表元信息（版本/统计/最近注册）
  - 本模块 = 唯一解析器 + 注册/去重/查询/统计 API

用法:
  python scripts/qbank.py init                          # 初始化注册表
  python scripts/qbank.py register --file <path> --batch batch026   # 注册单文件
  python scripts/qbank.py register --dir 中间产物 --dir 最终产物     # 递归注册目录
  python scripts/qbank.py stats                          # 全库统计
  python scripts/qbank.py query --stem 心衰 --type A1 --limit 10    # 查询
  python scripts/qbank.py check                          # 去重报告 + 完整性
  python scripts/qbank.py export-md --file <json> [--out <md>]  # 题库 → 可读 Markdown（最终交付格式）
  python scripts/qbank.py rehome [--dry-run]             # 修复归档后失效的注册路径
  python scripts/qbank.py --selftest                     # 解析器自检

设计约束: 仅标准库；register 幂等（(file,index) 已注册则跳过）；
去重只报告不删除（删除由人工决定）。
"""
import sys, json, os, re, hashlib, argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import gate_ledger

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REGISTRY_VERSION = 1

# ──────────────────────────────────────────
# 路径
# ──────────────────────────────────────────

_REG_BASE = None  # 测试接缝：临时注册表根目录（tests 用）


def _set_registry_base(base: str | Path | None) -> None:
    """测试用：将注册表读写重定向到临时目录（不污染真实注册表）。"""
    global _REG_BASE
    _REG_BASE = Path(base) if base else None


def base_dir() -> Path:
    return Path.cwd()


def _root() -> Path:
    return _REG_BASE if _REG_BASE else base_dir()


def registry_path() -> Path:
    return _root() / 'question_bank' / 'registry.jsonl'

def meta_path() -> Path:
    return _root() / 'question_bank' / 'registry_meta.json'

# ──────────────────────────────────────────
# 归档感知路径解析（2026-08-20 · 学期切换归档后注册表失效修复）
# ──────────────────────────────────────────

def _find_in_archive(rel):
    """在 archive/ 中按「相对路径后缀」查找已归档文件。

    学期切换（2026-08-19）把 中间产物/、最终产物/、复习资料/ 移入
    archive/ 后，注册表中旧相对路径失效。优先精确后缀匹配
    （如 中间产物\\batch019\\batch019_questions.json → archive\\中间产物\\batch019\\...），
    退化到 basename 唯一匹配（如 复习资料\\精神病学_统一题库_331题.json →
    archive\\复习资料历史_20260819\\精神病学_统一题库_331题.json）。
    """
    try:
        rel_norm = Path(rel).as_posix()
        name = Path(rel).name
    except Exception:
        return None
    archive_dir = _root() / 'archive'
    if not archive_dir.exists():
        return None
    # 1. 精确后缀匹配（最快路径，无歧义）
    for f in archive_dir.rglob(name):
        try:
            if f.is_file() and f.relative_to(archive_dir).as_posix().endswith(rel_norm):
                return f
        except ValueError:
            continue
    # 2. basename 唯一匹配（归档目录改名场景，如 复习资料历史_20260819）
    matches = [f for f in archive_dir.rglob(name) if f.is_file()]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_entry_path(rel: str) -> Path | None:
    """注册条目文件的实际路径：原位存在 → 原位；否则在 archive/ 中查找。"""
    p = _root() / rel
    if p.exists():
        return p
    alt = _find_in_archive(rel)
    return alt if alt else None


# ──────────────────────────────────────────
# 统一解析器：任意历史字段变体 → 规范结构
# ──────────────────────────────────────────

def parse_question(raw: dict[str, Any]) -> dict[str, Any] | None:
    """将任意格式的题目 dict 归一化为规范结构。无法识别返回 None。"""
    if not isinstance(raw, dict):
        return None
    stem = raw.get('stem') or raw.get('question') or raw.get('question_text') or raw.get('题干')
    if not stem or not isinstance(stem, str) or not stem.strip():
        return None

    q = {
        'qid': str(raw.get('question_id') or raw.get('id') or ''),
        'type': _norm_type(raw.get('type') or raw.get('question_type') or ''),
        'bloom_level': str(raw.get('bloom_level') or raw.get('bloom') or raw.get('认知层级') or ''),
        'module': str(raw.get('module') or raw.get('module_name') or ''),
        'stem': stem.strip(),
        'options': _norm_options(raw.get('options')),
        'answer': _norm_answer(raw.get('answer') or raw.get('answer_key') or raw.get('correct_answer')),
        'explanation': str(raw.get('explanation') or raw.get('analysis') or raw.get('解析') or ''),
        'source_pages': _norm_pages(raw),
        'source_pages_raw': (raw.get('source_pages') or raw.get('source_page') or raw.get('page') or ''),
    }
    return q


def _norm_type(t: str | int) -> str:
    t = str(t).strip()
    m = re.search(r'([A-Z]?\d?|X|判断)', t)
    if '判断' in t:
        return '判断'
    return t if t in ('A1', 'A2', 'A3', 'A4', 'B1', 'X') else t


def _norm_options(opts: dict | list | None) -> dict[str, str]:
    """options → {label: text}。兼容 dict / [{label,text}] / ['A. text']。"""
    out: dict[str, str] = {}
    if isinstance(opts, dict):
        for k, v in opts.items():
            if isinstance(v, str) and v.strip():
                out[str(k).strip().upper()] = v.strip()
    elif isinstance(opts, list):
        for o in opts:
            if isinstance(o, dict) and o.get('label') and o.get('text'):
                out[str(o['label']).strip().upper()] = str(o['text']).strip()
            elif isinstance(o, str):
                m = re.match(r'^([A-E])[.、）)\s]+(.*)$', o.strip())
                if m:
                    out[m.group(1)] = m.group(2).strip()
                elif o.strip():
                    out[str(len(out))] = o.strip()
    return out


def _norm_answer(ans):
    """答案归一化 → 大写字母串。

    v1.2 (2026-08-20 审查修复): 此前 re.search 只取**首个**字母，多选答案
    'ABD' 被截断成 'A'（实测复现）——注册表答案错误、export-md 只给 A 打 ✅
    而答案行显示 ABD，最终交付自相矛盾。现在优先整串匹配 [A-E]+；
    B1 复合答案 'E/A' 保持原样；非字母答案（判断/填空）保留原文首段。
    """
    if isinstance(ans, (list, tuple)):
        # X 型答案可能以列表形态出现（['A','C']）
        ans = ''.join(str(a).strip() for a in ans if str(a).strip())
    ans = str(ans or '').strip()
    upper = ans.upper()
    # B1 题组复合答案（如 'E/A'）保持原样
    if re.fullmatch(r'[A-E]/[A-E]', upper):
        return upper
    m = re.fullmatch(r'[A-E]+', upper)
    if m:
        return m.group(0)
    # 兼容 "答案：ABD" 等带前缀的表述
    m = re.search(r'[A-E]{2,}', upper)
    if m:
        return m.group(0)
    m = re.search(r'[A-E]', upper)
    if m:
        return m.group(0)
    return ans[:1] if ans else ''


def _norm_pages(raw):
    """source_pages → 页码 int 列表。

    v1.1 (2026-08-13): 仅提取 P 前缀页码（教材页码锚点），支持区间 P310-P312；
    指南年份（如"指南2023"）不再被误提取为页码。
    """
    pages = raw.get('source_pages') or raw.get('source_page') or raw.get('page') or ''
    if isinstance(pages, list):
        out = []
        for p in pages:
            out.extend(int(x) for x in re.findall(r'P\s*(\d+)', str(p)))
        return out
    if isinstance(pages, str):
        return [int(x) for x in re.findall(r'P\s*(\d+)', pages)]
    return []


def stem_hash(stem):
    """规范题干 → sha256。归一化: 去首尾空白 + 压缩内部空白。"""
    norm = re.sub(r'\s+', ' ', stem).strip()
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


def load_json_file(filepath):
    """读取 JSON 文件，返回 data 或 None（解析失败）。"""
    try:
        with open(filepath, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def extract_questions(filepath):
    """从题库文件中提取题目列表（列表顶层且含题干）。非题库文件返回 []。"""
    data = load_json_file(filepath)
    if not isinstance(data, list):
        return []
    questions = []
    for i, raw in enumerate(data):
        q = parse_question(raw)
        if q is not None:
            q['_index'] = i
            questions.append(q)
    return questions


# ──────────────────────────────────────────
# 注册表读写
# ──────────────────────────────────────────

def _read_entries():
    p = registry_path()
    if not p.exists():
        return []
    entries = []
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _append_entries(entries):
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'a', encoding='utf-8') as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(base_dir().resolve()))
    except ValueError:
        return str(path)


def _save_meta(stats):
    meta_path().parent.mkdir(parents=True, exist_ok=True)
    old = _read_meta()
    meta = {
        'schema_version': REGISTRY_VERSION,
        'updated_at': datetime.now().isoformat(),
        'stats': stats,
        # 保留既有豁免对（init --force 重建时不清空）
        'ignore_pairs': old.get('ignore_pairs', []),
    }
    with open(meta_path(), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def update_meta():
    """刷新注册表元信息（外部调用：ingest 注册后）。"""
    _save_meta(stats())


def init_registry_for_test():
    """程序化初始化空注册表（测试用，写入当前 _REG_BASE 指向的目录）。"""
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('', encoding='utf-8')
    _save_meta(stats())


# ──────────────────────────────────────────
# 注册（幂等 + 去重检测）
# ──────────────────────────────────────────

def register_file(filepath, batch, stage='standalone', base=None):
    """注册单文件题库。返回 (新注册数, 重复列表)。

    幂等: (file, index) 已注册则跳过（重新注册同一文件不产生重复条目）。
    去重: 与现有注册表 + 文件内比较 stem_hash，仅报告不删除。
    stage: final(最终产物) / intermediate(中间产物) / standalone(独立文件如押题卷)
    """
    base = Path(base) if base else base_dir()
    filepath = Path(filepath)
    rel = _rel(filepath)
    existing = _read_entries()
    existing_keys = {(e.get('file'), e.get('index')) for e in existing}
    existing_hashes = {e.get('stem_hash') for e in existing}

    questions = extract_questions(filepath)
    if not questions:
        return 0, []

    new_entries = []
    dups = []
    seen_in_file = {}
    for q in questions:
        key = (rel, q['_index'])
        if key in existing_keys:
            continue  # 幂等跳过
        h = stem_hash(q['stem'])
        if h in existing_hashes or h in seen_in_file:
            dups.append({
                'stem_hash': h,
                'stem': q['stem'][:60],
                'file': rel,
                'index': q['_index'],
                'dup_with_file': seen_in_file.get(h, '(注册表已有)'),
            })
        else:
            seen_in_file[h] = rel
        entry = {
            'schema_version': REGISTRY_VERSION,
            'qid': q['qid'],
            'stem_hash': h,
            'stem_snippet': q['stem'][:60],
            'batch': str(batch),
            'stage': stage,
            'file': rel,
            'index': q['_index'],
            'type': q['type'],
            'module': q['module'],
            'bloom_level': q['bloom_level'],
            'answer': q['answer'],
            'source_pages': q['source_pages'][:8],
            'status': 'active',
            'registered_at': datetime.now().isoformat(),
        }
        new_entries.append(entry)
        existing_hashes.add(h)

    if new_entries:
        _append_entries(new_entries)
    return len(new_entries), dups


def _final_batches():
    """最终产物中已含 FIXED 题库的批次集合（这些批次的中期产物视为被取代）。"""
    final_dir = base_dir() / '最终产物'
    result = set()
    if not final_dir.exists():
        return result
    for batch_dir in final_dir.iterdir():
        if batch_dir.is_dir() and any(batch_dir.glob('*FIXED*.json')):
            result.add(batch_dir.name)
    return result


def register_dir(dirs, batch_hint=None):
    """递归注册目录下所有题库 JSON。

    取代策略（铁律④ 精神）: 批次已有 最终产物/*FIXED*.json 时，
    跳过其 中间产物/ 原版（避免新旧版本重复注册）。
    返回 (注册数, 重复列表, 文件数)。
    """
    total_new = 0
    all_dups = []
    files_done = 0
    final_batches = _final_batches()
    for d in dirs:
        d = Path(d)
        if not d.is_absolute():
            d = base_dir() / d
        if not d.exists():
            print(f'  ⚠️ 目录不存在: {d}')
            continue
        for f in sorted(d.rglob('*.json')):
            if 'question_bank' in f.parts:
                continue
            rel = _rel(f)
            if '中间产物' in f.parts:
                batch = _infer_batch(f)
                if batch in final_batches:
                    continue  # 该批次最终版已注册，跳过中间版
                # 批次子目录内 → intermediate；根目录散落文件（押题卷/参考库）→ standalone
                stage = 'intermediate' if batch.startswith('batch') else 'standalone'
            elif '最终产物' in f.parts:
                batch = _infer_batch(f)
                stage = 'final'
            else:
                batch = batch_hint or _infer_batch(f)
                stage = 'standalone'
            n, dups = register_file(f, batch, stage=stage)
            if n or dups:
                files_done += 1
                total_new += n
                for dup in dups:
                    dup['batch'] = batch
                all_dups.extend(dups)
                print(f'  📄 {rel}: +{n} 题 ({stage})' + (f' ⚠️重复{len(dups)}' if dups else ''))
    return total_new, all_dups, files_done


def _infer_batch(path):
    """从路径推断批次号（batch026 → batch026；batch024-A → batch024-A；
    batch023_existing_ref → batch023-ref（合并来源参考文件）；
    predict 押题卷 → predict；其余 unknown）。"""
    parts = path.parts
    for p in parts:
        m = re.match(r'^(batch\d{3,}(?:-[A-Z])?)$', p)
        if m:
            return m.group(1)
    name = str(path)
    m2 = re.search(r'(batch\d{3,})_existing_ref', name)
    if m2:
        return m2.group(1) + '-ref'
    if 'predict' in name.lower():
        return 'predict'
    return 'unknown'


# ──────────────────────────────────────────
# 查询 / 统计 / 检查
# ──────────────────────────────────────────

def query(stem=None, qtype=None, module=None, bloom=None, batch=None, limit=20):
    """按条件查询注册表。"""
    entries = _read_entries()
    results = []
    for e in entries:
        if stem and stem not in e.get('stem_snippet', ''):
            continue
        if qtype and e.get('type') != qtype:
            continue
        if module and module not in e.get('module', ''):
            continue
        if bloom and bloom not in e.get('bloom_level', ''):
            continue
        if batch and e.get('batch') != batch:
            continue
        results.append(e)
        if len(results) >= limit:
            break
    return results


def stats():
    """全库统计。"""
    entries = _read_entries()
    from collections import Counter
    by_batch = Counter(e.get('batch', '?') for e in entries)
    by_type = Counter(e.get('type', '?') for e in entries)
    by_bloom = Counter(e.get('bloom_level', '?') or '未标注' for e in entries)
    return {
        'total': len(entries),
        'by_batch': dict(by_batch.most_common()),
        'by_type': dict(by_type.most_common()),
        'by_bloom': dict(by_bloom.most_common()),
        'schema_version': REGISTRY_VERSION,
    }


def _read_meta():
    """读取注册表元信息（含持久化的 ignore_pairs）。"""
    if meta_path().exists():
        try:
            with open(meta_path(), encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _persist_ignore_pairs(pairs):
    """持久化已知合并关系批次对到元信息（CLI --save 使用）。

    v1.2 (2026-08-20 审查修复 M4): 此前整体替换 meta 中已有的豁免集 ——
    多次 --save 互相清空对方（实测：5 对已持久化豁免被后续 3 对 --save 覆盖
    丢失，跨批次重复告警回潮 343 组）。现改为**合并追加**（只增不减）；
    如需删除请直接编辑 registry_meta.json 的 ignore_pairs。
    """
    meta = _read_meta()
    existing = set()
    for p in meta.get('ignore_pairs', []):
        if isinstance(p, list) and len(p) == 2:
            existing.add(frozenset(p))
    merged = existing | {frozenset(p) for p in pairs if len(p) == 2}
    meta['ignore_pairs'] = [sorted(p) for p in merged]
    meta['updated_at'] = datetime.now().isoformat()
    with open(meta_path(), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _effective_ignore_pairs(extra=None):
    """合并持久化 + 本次调用传入的豁免对。"""
    pairs = set()
    for p in _read_meta().get('ignore_pairs', []):
        if isinstance(p, list) and len(p) == 2:
            pairs.add(frozenset(p))
    if extra:
        pairs |= extra
    return pairs or None


def check(ignore_pairs=None):
    """去重报告 + 完整性检查。返回 (问题列表, 警告列表, 提示列表)。

    重复分类（2026-08-13 v1.1 / 2026-10-19 v1.3）:
      - 跨批次重复 = WARN（同一题干出现在两个不同批次，需人工裁决；
        可通过 --ignore-pair 豁免已知合并关系，如合并来源 vs 合并结果）
      - 同批次 multi-stage（intermediate/final 并存）= INFO（新版本取代旧版本，属预期）
      - 与非活动条目（status != 'active'，即 superseded / source_archived）重合 = INFO
        （v1.3：被取代的旧条目与新题重合属预期，不再计入 WARN）
    ignore_pairs: 集合 of frozenset({batchA, batchB}) — 豁免的批次对
                  （与 registry_meta.json 中持久化的对合并生效）
    """
    ignore_pairs = _effective_ignore_pairs(ignore_pairs)
    entries = _read_entries()
    from collections import defaultdict
    by_hash = defaultdict(list)
    for e in entries:
        by_hash[e.get('stem_hash')].append(e)
    issues = []
    warns = []
    infos = []
    ignored = 0
    for h, group in by_hash.items():
        if len(group) < 2:
            continue
        # v1.3 (2026-10-19): 非活动条目（status != 'active'，即 superseded /
        # source_archived）与新题重合属预期，降级为 INFO，不再计入 WARN
        # （旧批次被取代后其大量条目常与新版本少量条目重合，曾被报为
        #  "跨批次重复（需人工裁决）"）。
        if any(str(e.get('status', 'active')) != 'active' for e in group):
            infos.append(
                f'与非活动条目重合 x{len(group)}: 「{group[0].get("stem_snippet", "")}」'
                f' 批次={sorted({e.get("batch") for e in group})}'
                f' 状态={sorted({str(e.get("status", "active")) for e in group})}'
            )
            continue
        batches = {e.get('batch') for e in group}
        if len(batches) > 1:
            sample = group[0]
            # v1.2 (2026-08-20 审查修复 M4/L): 豁免判定从"整个重复组的批次集合
            # 精确命中豁免对"放宽为"组内批次两两组合全部在豁免对中"——
            # 此前 3+ 批次组合（如 batch007/batch023-ref/psychiatry-merged 同源
            # 三表示）永远无法豁免，已持久化的成对豁免形同虚设
            if ignore_pairs:
                bs = set(batches)
                pairs_ok = True
                for a in bs:
                    for b in bs:
                        if a != b and frozenset({a, b}) not in ignore_pairs:
                            pairs_ok = False
                            break
                    if not pairs_ok:
                        break
                if pairs_ok:
                    ignored += 1
                    continue
            warns.append(
                f'跨批次重复 x{len(group)}: 「{sample.get("stem_snippet", "")}」'
                f' 批次={sorted(batches)}'
            )
        else:
            sample = group[0]
            infos.append(
                f'同批次多版本 x{len(group)}: 「{sample.get("stem_snippet", "")}」'
                f' 批次={sample.get("batch")} (stage={sorted({e.get("stage") for e in group})})'
            )
    # 完整性: 引用文件存在（支持 archive/ 归档回退，2026-08-20）
    # v1.3 (2026-10-19): 仅校验 status == 'active' 的条目——已取代/源已归档
    # 的条目其源文件按学期归档制度本就可能不在工作区，继续硬报会让完整性检查长期 FAIL。
    missing = set()
    for e in entries:
        if str(e.get('status', 'active')) != 'active':
            continue
        if resolve_entry_path(e.get('file', '')) is None:
            missing.add(e.get('file'))
    if missing:
        issues.append(f'{len(missing)} 个注册文件不存在: {sorted(missing)[:5]}')
    # 元信息
    meta = {}
    if meta_path().exists():
        with open(meta_path(), encoding='utf-8') as f:
            meta = json.load(f)
    if entries and meta.get('schema_version') != REGISTRY_VERSION:
        issues.append(f'meta schema_version={meta.get("schema_version")} 与当前 {REGISTRY_VERSION} 不一致')
    if ignored:
        infos.append(f'已豁免已知合并关系 {ignored} 组（--ignore-pair）')
    return issues, warns, infos


# ──────────────────────────────────────────
# 注册表路径重定位 rehome（2026-08-20 新增）
# ──────────────────────────────────────────

def rehome(dry_run=False):
    """将注册表中失效的条目路径重写为 archive/ 下的实际位置。

    学期切换归档后，14 条注册指向已移入 archive/ 的文件。
    check() 已支持归档回退（只读感知）；rehome 则把路径**持久化修正**，
    使 qbank 下游（query/去重/统计）继续使用活动路径语义。

    返回 (重写条数, 仍缺失条数)。
    """
    entries = _read_entries()
    if not entries:
        return 0, 0
    rewritten = 0
    still_missing = 0
    for e in entries:
        rel = e.get('file', '')
        if not rel:
            continue
        if (base_dir() / rel).exists():
            continue  # 原位存在，无需处理
        alt = _find_in_archive(rel)
        if alt is None:
            still_missing += 1
            continue
        new_rel = str(alt.relative_to(base_dir().resolve())) if alt.is_relative_to(base_dir().resolve()) else str(alt)
        e['file'] = new_rel
        rewritten += 1
    if rewritten and not dry_run:
        # 原子重写 registry.jsonl
        tmp = registry_path().with_suffix('.jsonl.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')
        tmp.replace(registry_path())
    return rewritten, still_missing


# ──────────────────────────────────────────
# MD 导出（2026-08-20 新增 · 最终交付格式）
# ──────────────────────────────────────────

TYPE_NAMES = {'A1': 'A1型题', 'A2': 'A2型题', 'A3': 'A3型题', 'A4': 'A4型题',
              'B1': 'B1型题', 'X': 'X型题', '判断': '判断题'}


def export_md(filepath, outpath=None, title=None):
    """题库 JSON → 可读 Markdown（最终交付格式）。

    基于统一解析器 parse_question（兼容 6 种历史字段变体），
    按模块分组输出，正确选项用 ✅ 标记 + 加粗，附答案/解析/页码/Bloom。
    默认输出到源文件同目录同名 .md。

    返回 (输出路径, 题数)；非题库文件返回 (None, 0)。
    """
    data = load_json_file(filepath)
    if not isinstance(data, list):
        print(f'✗ {filepath} 不是题库 JSON（顶层非数组），跳过导出')
        return None, 0

    questions = []
    for i, raw in enumerate(data):
        q = parse_question(raw)
        if q is not None:
            q['_index'] = i
            q['_raw'] = raw
            questions.append(q)
    if not questions:
        print(f'✗ {filepath} 未解析出任何题目，跳过导出')
        return None, 0

    # 模块分组（兼容 module / module_name / 中文键）
    from collections import OrderedDict
    by_module = OrderedDict()
    for q in questions:
        mod = q.get('module') or '未分组'
        by_module.setdefault(mod, []).append(q)

    if title is None:
        title = Path(filepath).stem.replace('_FIXED', '').replace('_questions', '')
    if outpath is None:
        outpath = str(Path(filepath).with_suffix('.md'))

    from collections import Counter
    type_counter = Counter(q['type'] or '?' for q in questions)
    bloom_counter = Counter(q['bloom_level'] or '未标注' for q in questions)

    lines = []
    lines.append(f'# {title} 题库（{len(questions)}题）')
    lines.append('')
    lines.append(f'> 来源：{_rel(filepath)} | 导出：{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    lines.append(f'> 题型分布：{"、".join(f"{k}×{v}" for k, v in type_counter.most_common())}')
    lines.append(f'> Bloom分布：{"、".join(f"{k}×{v}" for k, v in bloom_counter.most_common())}')
    lines.append('')
    lines.append('---')
    lines.append('')

    seq = 0
    for mod, qs in by_module.items():
        lines.append(f'## {mod}（{len(qs)}题）')
        lines.append('')
        for q in qs:
            seq += 1
            qt = TYPE_NAMES.get(q.get('type', ''), q.get('type') or '未知')
            bl = q.get('bloom_level') or '未标注'
            qid = q.get('qid') or f'Q{q["_index"]+1}'
            lines.append(f'### {seq}. [{qt}｜{bl}] {qid}')
            lines.append('')
            # 溯源/页码
            pages_raw = q.get('source_pages_raw') or ''
            if not pages_raw and q.get('source_pages'):
                pages_raw = 'P' + ',P'.join(str(p) for p in q['source_pages'])
            meta = f'模块：{mod}'
            if pages_raw:
                meta += f'｜页码：{pages_raw}'
            lines.append(f'> {meta}')
            lines.append('')
            lines.append(f'**{q["stem"]}**')
            lines.append('')
            ans = q.get('answer') or ''
            raw_ans = ''
            raw = q.get('_raw') or {}
            raw_ans = str(raw.get('answer') or raw.get('answer_key') or raw.get('correct_answer') or '')
            opts = q.get('options') or {}
            if opts:
                # v1.2 (2026-08-20 审查修复): 多选（X 型）答案逐字母标记 ✅，
                # 此前只标记首个字母（'ABD' → 仅 A 打 ✅），与答案行自相矛盾
                correct_letters = {c for c in str(ans).upper() if c in 'ABCDE'}
                for label in sorted(opts.keys()):
                    text = opts[label]
                    if label.upper() in correct_letters:
                        lines.append(f'- **{label}. {text}** ✅')
                    else:
                        lines.append(f'- {label}. {text}')
            lines.append('')
            if raw_ans:
                # 判断/填空类答案保留原文（如"正确/错误"），字母答案显示字母
                lines.append(f'**答案：{raw_ans}**')
            else:
                lines.append(f'**答案：（未标注）**')
            expl = q.get('explanation') or ''
            if expl:
                lines.append('')
                lines.append(f'> 解析：{expl}')
            lines.append('')
            lines.append('---')
            lines.append('')

    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    size_kb = os.path.getsize(outpath) / 1024
    print(f'✅ MD 导出: {outpath}（{len(questions)}题 / {len(lines)}行 / {size_kb:.1f}KB）')
    return outpath, len(questions)


# ──────────────────────────────────────────
# 自检
# ──────────────────────────────────────────

def selftest():
    """解析器 + 注册表逻辑自检（零依赖）。"""
    ok = True
    # 1. 三种 options 格式
    q1 = parse_question({'question': '心衰诊断金标准?', 'options': {'A': 'a', 'B': 'b'},
                         'answer': 'A', 'id': 'T1'})
    q2 = parse_question({'stem': '心衰诊断金标准?', 'options': [{'label': 'A', 'text': 'a'}, {'label': 'B', 'text': 'b'}],
                         'answer_key': 'B', 'question_id': 'T2'})
    q3 = parse_question({'question_text': '心衰诊断金标准?', 'options': ['A. a', 'B. b'],
                         'correct_answer': 'C', 'id': 'T3'})
    assert q1 and q1['answer'] == 'A' and 'A' in q1['options'], 'q1 parse fail'
    assert q2 and q2['answer'] == 'B' and 'B' in q2['options'], 'q2 parse fail'
    assert q3 and q3['answer'] == 'C' and 'A' in q3['options'], 'q3 parse fail'
    assert q1['stem'] == q2['stem'] == q3['stem'], 'stem mismatch'
    assert stem_hash(q1['stem']) == stem_hash('  心衰诊断金标准?  '), 'stem_hash normalize fail'
    print('  ✓ 三种 options 格式 + stem_hash 归一化')
    # 2. 非题库数据
    assert parse_question({'report_metadata': {}}) is None, 'dict without stem should be None'
    assert extract_questions('/nonexistent.json') == [], 'missing file should be []'
    print('  ✓ 非题库数据容错')
    print('SELFTEST_PASS')
    return ok


# ──────────────────────────────────────────
# CLI
# ──────────────────────────────────────────

# ──────────────────────────────────────────
# 交付口验真（v2.5.0 防跳过层）
# ──────────────────────────────────────────

def _delivery_batch(out) -> str | None:
    """输出路径落在 最终产物/{batch}/ 时返回批次目录名（原样，可能不合规）；否则 None。

    用 `resolve()` 后再取路径段：防 `最终产物/batch001/../../最终产物/batch1/x.md`
    这类「路径段写 batch001、实际落点 batch1」的绕过。
    """
    if out is None:
        return None
    p = Path(out)
    try:
        parts = p.resolve().parts
    except Exception:
        parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part == '最终产物':
            if i > 0 and parts[i - 1] == 'archive':
                return None  # 归档区不拦截（交付口只认工作区 最终产物/）
            return parts[i + 1] or None
    return None


def _lv_applicable(batch: str) -> bool:
    """交付口用的 lv 适用性：读交付 JSON 的 schema_version（>=2.0 且非空）。"""
    p = Path('最终产物') / batch / 'ALL_questions_FIXED.json'
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return False
    if isinstance(data, dict):
        data = data.get('questions')
    for q in data or []:
        if not isinstance(q, dict):
            continue
        try:
            if float(str(q.get('schema_version') or '0')) >= 2.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _require_delivery_receipt(batch: str, input_file, out_path) -> int:
    """交付口硬闸：往 最终产物/{batch}/ 写交付 MD 前，验 A2/A3/A4 回执 + A4 字节绑定。

    这是 v2.5.0「防跳过」与宿主无关的一层：不读规则的 agent 软件也会在这里被拒。
    只约束 `qbank.py export-md` 这条路径；绕开 CLI 直接写文件属本地边界（见 README）。
    """
    print(f'=== 交付口验真：{batch}（v2.5.0 防跳过）===')
    if not gate_ledger.BATCH_RE.match(str(batch)):
        print(f'✗ 交付被拒：BATCH_NAME_INVALID —— 批次目录 {batch!r} 不符合 batchNNN 命名。')
        print('  交付口与 gate_audit 都按 batchNNN 识别批次；不合规命名 = 防护静默失效。')
        return 1
    report = gate_ledger.verify(batch, 'a4', require_artifacts=[input_file])
    if report['verdict'] == 'FAIL':
        detail = next((c['detail'] for c in report['checks'] if c['status'] == 'FAIL'), '')
        print(f"✗ 交付被拒：{report['code']} —— {detail}")
        print('  没有有效 A4 回执的交付物不可写入 最终产物/：跳过门禁 = 拿不到交付件。')
        # 按回执链现状给出正确的补齐起点（缺 a2 → 从 a2 起；缺 a3 → 从 a3 起）
        led0, _ = gate_ledger.load_ledger(batch)
        have = {st.get('stage') for st in (led0 or {}).get('stamps') or []}
        todo = [s for s in ('a2', 'a3', 'a4') if s not in have] or ['a4']
        print(f'  → 按顺序补跑：python {{SKILL}}/scripts/gate_run.py --batch {batch} --stage ' + ' → '.join(todo))
        return 1
    led, err = gate_ledger.load_ledger(batch)
    if led is None:
        print(f"✗ 交付被拒：{err or '回执链不可读'}")
        return 1
    first_seq = {}
    for st in led.get('stamps') or []:
        first_seq.setdefault(st.get('stage'), st.get('seq'))
    missing = [s for s in ('a2', 'a3', 'a4') if s not in first_seq]
    if missing:
        print(f"✗ 交付被拒：STAGE_MISSING —— 回执链缺少前置阶段 {', '.join(missing)}（跳过门禁）")
        print(f'  → 按顺序补跑：gate_run.py --batch {batch} --stage ' + ' → '.join(missing))
        return 1
    if not (first_seq['a2'] < first_seq['a3'] < first_seq['a4']):
        print('✗ 交付被拒：STAGE_ORDER —— 回执链阶段顺序不是 a2 → a3 → a4（回执被重排/伪造）')
        return 1
    if _lv_applicable(batch) and 'lv' not in first_seq:
        print('✗ 交付被拒：STAGE_MISSING —— schema 2.0+ 批次缺少 lv 回执（HC-24 学习价值门禁被跳过）')
        print(f'  → 补跑：gate_run.py --batch {batch} --stage lv')
        return 1
    if report['verdict'] == 'WARN':
        print(f"⚠️ 回执可用但含 SKIPPED 子门禁：{report['code']}（继续交付，gate_audit 会记 WARN）")
    print(f"✓ A2/A3/A4 回执有效（a4 seq={report['stamp_seq']}），放行交付 → {out_path}")
    return 0


def _stamp_export(batch: str, md_path, json_path) -> None:
    """导出成功后把交付 MD 字节追加进回执链（stage=export）。

    A4 回执绑定 JSON 源；交付 MD 是真正交到用户手上的文件，必须单独字节绑定，
    否则「导出后手改 MD」无法被审计发现。重跑 export 会追加新回执（以最新为准）。
    """
    led, err = gate_ledger.load_ledger(batch)
    if led is None:
        print(f'⚠️ export 回执未写：{err or "回执链缺失"}（交付 MD 未被绑定）')
        return
    gate_ledger.append_stamp(
        led, 'export', artifacts=[md_path, json_path],
        gates=[{'id': 'EXPORT-MD', 'argv': ['qbank.py', 'export-md'], 'rc': 0}],
        provenance='export-md', tool='qbank@2.5.0', note='交付 MD 生成并绑定字节')
    try:
        gate_ledger.write_ledger(led)
        print(f'✓ 已绑定交付 MD 回执：{gate_ledger.ledger_path(batch)}')
    except OSError as exc:
        print(f'⚠️ export 回执写入失败：{exc}（交付 MD 未被绑定，gate_audit 会判缺阶段）')


def main():
    parser = argparse.ArgumentParser(description='MedAgentWork 统一题库数据层 (qbank)')
    sub = parser.add_subparsers(dest='cmd')

    p_init = sub.add_parser('init', help='初始化注册表')
    p_init.add_argument('--force', action='store_true', help='清空重建')

    p_reg = sub.add_parser('register', help='注册题库文件/目录')
    p_reg.add_argument('--file', '-f')
    p_reg.add_argument('--dir', '-d', action='append', default=[])
    p_reg.add_argument('--batch', '-b', help='批次号（--file 模式必填）')

    p_q = sub.add_parser('query', help='查询')
    p_q.add_argument('--stem', default=None)
    p_q.add_argument('--type', default=None)
    p_q.add_argument('--module', default=None)
    p_q.add_argument('--bloom', default=None)
    p_q.add_argument('--batch', default=None)
    p_q.add_argument('--limit', type=int, default=20)
    p_q.add_argument('--json', action='store_true', help='JSON 输出')

    sub.add_parser('stats', help='全库统计')
    p_check = sub.add_parser('check', help='去重报告 + 完整性')
    p_check.add_argument('--ignore-pair', action='append', default=[],
                         metavar='batchA,batchB',
                         help='豁免已知合并关系的批次对（如 batch023-ref,psychiatry-merged）')
    p_check.add_argument('--save', action='store_true',
                         help='将 --ignore-pair 持久化到 registry_meta.json（healthcheck 自动读取）')

    p_md = sub.add_parser('export-md', help='题库 JSON → 可读 Markdown（最终交付格式）')
    p_md.add_argument('--file', '-f', required=True, help='题库 JSON 路径')
    p_md.add_argument('--out', '-o', default=None, help='输出 .md 路径（默认同目录同名）')
    p_md.add_argument('--title', '-t', default=None, help='MD 标题（默认取文件名）')

    p_rehome = sub.add_parser('rehome', help='重写注册表中归档后失效的文件路径')
    p_rehome.add_argument('--dry-run', action='store_true', help='只报告不写入')

    parser.add_argument('--selftest', action='store_true', help='解析器自检')
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    if args.cmd == 'init':
        if registry_path().exists() and not args.force:
            print('✗ 注册表已存在（--force 清空重建）')
            sys.exit(1)
        registry_path().parent.mkdir(parents=True, exist_ok=True)
        registry_path().write_text('', encoding='utf-8')
        _save_meta(stats())
        print(f'✓ 注册表已初始化: {registry_path()}')
        return

    if args.cmd == 'register':
        if args.file:
            if not args.batch:
                print('✗ --file 模式必须提供 --batch')
                sys.exit(1)
            n, dups = register_file(args.file, args.batch)
            print(f'✓ {args.file}: 新注册 {n} 题' + (f'，重复 {len(dups)} 条' if dups else ''))
            for d in dups[:10]:
                print(f'  ⚠️ 「{d["stem"]}」 ← {d["dup_with_file"]}')
        elif args.dir:
            n, dups, files = register_dir(args.dir, args.batch)
            print(f'✓ 共注册 {files} 个文件 / {n} 题' + (f'，重复 {len(dups)} 条' if dups else ''))
            for d in dups[:10]:
                print(f'  ⚠️ 「{d["stem"]}」 ← {d.get("dup_with_file")}')
        else:
            print('✗ 需要 --file 或 --dir')
            sys.exit(1)
        _save_meta(stats())
        return

    if args.cmd == 'stats':
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
        return

    if args.cmd == 'query':
        results = query(args.stem, args.type, args.module, args.bloom, args.batch, args.limit)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f'命中 {len(results)} 条:')
            for e in results:
                print(f'  [{e.get("batch")}] {e.get("type", "?"):4s} {e.get("module", "?"):6s} '
                      f'{e.get("bloom_level", "?"):8s} {e.get("answer", "?"):2s} {e.get("stem_snippet", "")}')
        return

    if args.cmd == 'check':
        ignore_pairs = None
        if args.ignore_pair:
            ignore_pairs = set()
            for pair in args.ignore_pair:
                a, _, b = pair.partition(',')
                if a and b:
                    ignore_pairs.add(frozenset({a.strip(), b.strip()}))
            if args.save:
                _persist_ignore_pairs(ignore_pairs)
                print(f'✓ 已持久化 {len(ignore_pairs)} 个豁免批次对 → registry_meta.json')
        issues, warns, infos = check(ignore_pairs)
        s = stats()
        print(f'注册表: {s["total"]} 题 | schema v{s["schema_version"]}')
        if warns:
            print(f'⚠️ 跨批次重复 {len(warns)} 组（需人工裁决）:')
            for w in warns[:20]:
                print(f'  {w}')
            if len(warns) > 20:
                print(f'  ... 共 {len(warns)} 组')
        else:
            print('✓ 无跨批次重复题干')
        if infos:
            print(f'ℹ️ 同批次多版本 {len(infos)} 组（新版本取代旧版本，属预期）:')
            for i in infos[:5]:
                print(f'  {i}')
            if len(infos) > 5:
                print(f'  ... 共 {len(infos)} 组')
        if issues:
            print(f'✗ {len(issues)} 个问题:')
            for i in issues:
                print(f'  {i}')
            sys.exit(1)
        else:
            print('✓ 完整性通过')
        return

    if args.cmd == 'export-md':
        out_target = Path(args.out) if args.out else Path(args.file).with_suffix('.md')
        batch = _delivery_batch(out_target)
        if batch:
            rc = _require_delivery_receipt(batch, args.file, out_target)
            if rc:
                sys.exit(rc)
        out, n = export_md(args.file, args.out, args.title)
        if out is None:
            sys.exit(1)
        if batch:
            try:
                md_abs = Path(out).resolve()
                json_abs = Path(args.file).resolve()
            except Exception:
                md_abs, json_abs = out, args.file
            _stamp_export(batch, md_abs, json_abs)
        return

    if args.cmd == 'rehome':
        rewritten, missing = rehome(dry_run=args.dry_run)
        if args.dry_run:
            print(f'ℹ️ dry-run：可重写 {rewritten} 条' + (f'，仍缺失 {missing} 条' if missing else ''))
        else:
            print(f'✅ 已重写 {rewritten} 条注册路径' + (f'，仍缺失 {missing} 条' if missing else ''))
        return

    parser.print_help()


if __name__ == '__main__':
    main()
