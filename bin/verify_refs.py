# -*- coding: utf-8 -*-
"""历史印证一查多注（共享模块，liupan/make 同源调用）：
结构化属性匹配（宫位+星系+四化精确匹配，扫账本 jsonl）为主，
FAISS 向量相似度退为无结构命中时的模糊参考兜底（embed.py --query top-K）。
匹配结果按 person 分组（自身=一级/跨命主=二级），两级结论一致标"加强印证"（纯文字）。
两层架构注入——只注入抽象经验链（配置+预测+结果），不注入原始事件叙事。
经验链扩展：增含 theory 分析过程（宫位判定+语料引用+推理+对照——子代理可见完整推理链）。
按事件类别路由宫位 → 注入对应宫 input【历史印证参考】节 + 命中落批次 verify_refs.json。
零第三方依赖（FAISS 兜底走独立 venv 子进程）。查询失败容错：警告+空 verify_refs.json，不阻断批次。
"""
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
EMBED_PY = os.path.join(SKILL_ROOT, 'verify', 'bin', 'embed.py')
BIN_DIR = os.path.join(SKILL_ROOT, 'verify', 'bin')

# 事件类别→宫位路由表（注入落点；人际事件细分归宫）
CATEGORY_PALACES = {
    '交易盈亏': ['财帛'],
    '人际事件': ['父母', '仆役', '兄弟'],
    '出行': ['迁移'],
    '健康': ['疾厄'],
    '意外': ['疾厄', '迁移'],
    '情绪波动': ['福德'],
    '重要决策': ['命宫', '官禄'],
    '口舌是非': ['仆役', '迁移'],
}

INPUT_RE = re.compile(r'^input_\d+_(.+)\.md$')
MAIN14 = {'紫微', '天机', '太阳', '武曲', '天同', '廉贞', '天府', '太阴',
          '贪狼', '巨门', '天相', '天梁', '七杀', '破军'}
ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

PRED_OK = '预测准确'
PRED_BAD = '预测不准'


def vec_python():
    """Python 解释器：anchors PYTHON_VEC；缺席退 sys.executable（faiss 缺失时查询步自然告警跳过）。"""
    cur = HERE
    for _ in range(8):
        path = os.path.join(cur, 'anchors.json')
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    val = json.load(f).get('PYTHON_VEC')
                if val:
                    return val
            except (OSError, ValueError):
                break
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return sys.executable


def _run_embed(args):
    env = dict(os.environ, PYTHONUTF8='1')
    r = subprocess.run([vec_python(), EMBED_PY] + args, capture_output=True, env=env,
                       timeout=120, cwd=SKILL_ROOT)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace').strip() or '未知错误')
    return r.stdout.decode('utf-8', 'replace')


def serialize_via_embed(combo_features, layer=None):
    """标准序列化文本：子进程调 embed.py --serialize（唯一出口，禁自行拼）。
    layer 给定=层别序列化（层内精确比对）。"""
    args = ['--serialize', json.dumps(combo_features, ensure_ascii=False)]
    if layer:
        args += ['--layer', layer]
    return _run_embed(args).strip()


def query_verify_refs(combo_features, exclude_date=None, data_dir=None, top_k=5, layer=None):
    """一查：combo → top-K 历史相似事件（layer 给定=层别查询，同层比对；
    embed.py 已过滤阈值与 ≥分析日期事件）。层别向量仅 liuri/liuyue/liunian 事件持有，
    其余层（daxian/liushi）自动退全盘查询。"""
    if layer not in ('liuri', 'liuyue', 'liunian'):
        layer = None  # 向量路径：liushi/daxian 维持全盘退（embed 层别向量不扩，v8 定案）
    args = ['--query', serialize_via_embed(combo_features, layer=layer),
            '--top-k', str(top_k)]
    if layer:
        args += ['--layer', layer]
    if exclude_date:
        args += ['--exclude-date', exclude_date]
    if data_dir:
        args += ['--data-dir', data_dir]
    return json.loads(_run_embed(args))


def _date_sort_key(date_str):
    """排序键：日期段 + 时支序（时辰级 YYYY-MM-DD-支 按支序排，非 Unicode 序）。"""
    s = date_str or ''
    if len(s) > 10 and s[10] == '-' and s[11:] in ZHI:
        return (s[:10], ZHI.index(s[11:]))
    return (s, -1)


def structured_query(combo, cur_person, exclude_date=None, data_dir=None, layer=None):
    """结构化属性匹配：宫位+星系+四化精确匹配，直接扫账本 jsonl（替代 FAISS 为主）。
    匹配键：layer_ming_xingxi（命宫星系）完全相等 + sihua 四化集（星@支）完全相等。
    未来函数修正：排除 event_date ≥ exclude_date 的记录。layer 给定时优先同层事件。
    返回 hit 列表（含 person/category/date/prediction/outcome/verify_result——经验链字段）。"""
    sys.path.insert(0, BIN_DIR)
    from common import list_shards, read_lines, resolve_data_dir
    data_dir = resolve_data_dir(data_dir)
    q_xingxi = (combo or {}).get('layer_ming_xingxi', '')
    q_sihua = {h: (v or '').split('(')[0]
               for h, v in ((combo or {}).get('sihua') or {}).items() if v}
    q_key = (q_xingxi, tuple(sorted(q_sihua.items())))
    level_cn = {'liuri': '流日', 'liuyue': '流月', 'liunian': '流年', 'liushi': '流时'}.get(layer or '')
    hits = []
    for _, _, name in list_shards(data_dir):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            cf = rec.get('combo_features') or {}
            if not cf:
                continue
            date = rec.get('event_date', '')
            if exclude_date and date >= exclude_date:
                continue
            e_xingxi = cf.get('layer_ming_xingxi', '')
            e_sihua = {h: (v or '').split('(')[0]
                       for h, v in (cf.get('sihua') or {}).items() if v}
            if (e_xingxi, tuple(sorted(e_sihua.items()))) != q_key:
                continue
            hits.append({
                'person': rec.get('person', ''),
                'category': rec.get('category', ''),
                'date': date,
                'prediction': rec.get('prediction', ''),
                'outcome': rec.get('outcome', ''),
                'verify_result': rec.get('verify_result', ''),
                'text': rec.get('text', ''),
                'theory': rec.get('theory', ''),
                'layer': rec.get('level', ''),
                'liuyue_label': (rec.get('structure_snapshot') or {}).get('liuyue_label', ''),
            })
    # 同层优先排序：与查询层同名（拼音口径；兼容存量中文值）的事件排前（跨层参考居后）；
    # 同日时辰级（YYYY-MM-DD-支）按支序排（支序非 Unicode 序）
    same = {layer or '', level_cn} - {''}
    hits.sort(key=lambda h: (h['layer'] not in same, _date_sort_key(h['date'])))
    return hits


GATE = 1  # 注入闸门（干支直查制 v2.0）：三层各 1 条即注入

GAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
# 干支直查基准：2026-10-21=戊辰日（干支历 60 甲子循环锚点）
GANZHI_ANCHOR = ('2026-10-21', 4, 4)  # (日期, 戊在GAN序, 辰在ZHI序)

import datetime


def get_day_ganzhi(date_str):
    """日期 → (流日天干, 流日地支)；60 甲子循环，基准 2026-10-21=戊辰。
    时辰级日期（YYYY-MM-DD-支）取前 10 位日期段。不可解析返回 (None, None)。"""
    if not isinstance(date_str, str):
        return None, None
    date_str = date_str[:10]  # 拆时支后缀（时辰级键形）与月末 day 形态超长段
    try:
        d = datetime.date(*map(int, date_str.split('-')))
    except (TypeError, ValueError):
        return None, None
    anchor = datetime.date(*map(int, GANZHI_ANCHOR[0].split('-')))
    diff = (d - anchor).days
    return GAN[(GANZHI_ANCHOR[1] + diff) % 10], ZHI[(GANZHI_ANCHOR[2] + diff) % 12]


def _hit_fields(rec):
    """账本行 → 经验链字段（L1/L2/L3 共用显示口径）。"""
    return {
        'event_id': rec.get('event_id', ''),
        'person': rec.get('person', ''),
        'category': rec.get('category', ''),
        'date': rec.get('event_date', ''),
        'prediction': rec.get('prediction', ''),
        'outcome': rec.get('outcome', ''),
        'verify_result': rec.get('verify_result', ''),
        'text': rec.get('text', ''),
        'theory': rec.get('theory', ''),
        'layer': rec.get('level', ''),
        'liuyue_label': (rec.get('structure_snapshot') or {}).get('liuyue_label', ''),
    }


def _event_palace_info(rec):
    """记录应验宫快照条目 -> (宫名, info) or (None, None)。
    单宫记键：只从 event_palace 定位；无该字段/快照缺宫=fail-fast 跳过，
    禁 fallback 全盘（结构在场≠结构应验）。"""
    ep = rec.get('event_palace')
    if not ep:
        return None, None
    info = ((rec.get('structure_snapshot') or {}).get('palaces') or {}).get(ep)
    if not isinstance(info, dict):
        return None, None
    return ep, info


def _rec_palace_zhi(rec):
    """记录应验宫地支（无 event_palace/快照/地支返回 None，单宫记键禁 fallback）。"""
    _, info = _event_palace_info(rec)
    if info is None:
        return None
    return info.get('zhi') or None


def record_panxing_keys(rec):
    """盘型级键集合 {(流日天干, 流日地支)}——干支直查制（
    天干唯一决定四化、地支唯一决定星系排布，(干,支) 即整盘指纹）。"""
    gan, zhi = get_day_ganzhi(rec.get('event_date', ''))
    if gan is None:
        return set()
    return {(gan, zhi)}


def record_xingxi_keys(rec):
    """星系级键集合 {(流日天干, 应验宫地支)}——同干异支：四化同款，宫名挂位不同
    但应验宫恰坐同地支（同款星系）；无应验宫地支不生成键。"""
    gan, _ = get_day_ganzhi(rec.get('event_date', ''))
    if gan is None:
        return set()
    pz = _rec_palace_zhi(rec)
    if pz is None:
        return set()
    return {(gan, pz)}


def record_gongwei_keys(rec):
    """宫位级键集合 {(流日地支, 应验宫地支)}——同支异干：盘面排布全同（同宫同星同地支），
    仅四化不同；无应验宫地支不生成键。"""
    _, zhi = get_day_ganzhi(rec.get('event_date', ''))
    if zhi is None:
        return set()
    pz = _rec_palace_zhi(rec)
    if pz is None:
        return set()
    return {(zhi, pz)}


def layered_query(structure_snapshot, exclude_date=None, data_dir=None):
    """干支直查制三层互斥查询（v2.0）：
    盘型级=历史(干,支)==今日(干,支)；星系级=同干+异支+应验宫地支==今日某宫地支；
    宫位级=异干+同支+应验宫名==今日同宫名（同支=盘面同=同宫同地支自动成立）。
    一条事件只归一个最高级（互斥不嵌套）；闸门 GATE=1（一条即注入）。
    返回 {'panxing': [...], 'xingxi': [...], 'gongwei': [...]}（hit 含 _palace/_palace_zhi）。
    分析日取 exclude_date（YYYY-MM-DD）；非完整日期（流月/流年层）干支直查不适用，返回空。"""
    sys.path.insert(0, BIN_DIR)
    from common import list_shards, read_lines, resolve_data_dir
    empty = {'panxing': [], 'xingxi': [], 'gongwei': []}
    t_gan, t_zhi = get_day_ganzhi(exclude_date or '')
    if t_gan is None:
        return empty
    palaces = ((structure_snapshot or {}).get('palaces') or {})
    if not palaces:
        return empty
    today_zhi_values = {info.get('zhi') for info in palaces.values() if info.get('zhi')}
    data_dir = resolve_data_dir(data_dir)
    for _, _, name in list_shards(data_dir):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not (rec.get('combo_features') or rec.get('structure_snapshot')):
                continue
            date = rec.get('event_date', '')
            if not date:
                continue
            if exclude_date and date >= exclude_date:
                continue
            gan, zhi = get_day_ganzhi(date)
            if gan is None:
                continue
            ep, _ = _event_palace_info(rec)
            pz = _rec_palace_zhi(rec)
            hit = _hit_fields(rec)
            hit['_palace'] = ep or ''
            hit['_palace_zhi'] = pz or ''
            if gan == t_gan and zhi == t_zhi:
                empty['panxing'].append(hit)
            elif gan == t_gan and zhi != t_zhi and pz in today_zhi_values:
                empty['xingxi'].append(hit)
            elif gan != t_gan and zhi == t_zhi and ep in palaces:
                empty['gongwei'].append(hit)
    return empty


def origin_combo(pan):
    """原局盘 combo_features（make.py 原局链查询用；星系口径同 extractor.build_combo）。"""
    ming = pan.get('mingShen', {}).get('ming', '')
    star_map = pan.get('allStarMap', {})
    by = [s for s, z in star_map.items() if z == ming]
    main = [s for s in by if s in MAIN14]
    minor = [s for s in by if s not in MAIN14]
    xingxi = ''.join(main)
    if not xingxi:
        opp = ZHI[(ZHI.index(ming) + 6) % 12] if ming in ZHI else ''
        o_main = [s for s, z in star_map.items() if z == opp and s in MAIN14]
        if o_main:
            xingxi = '借' + ''.join(o_main) + '(%s)' % opp
    if minor:
        xingxi = ('%s+' % xingxi if xingxi else '') + ''.join(minor)
    tp = pan.get('twelvePalaces', {})
    sihua = {}
    for h, ent in (pan.get('siHua') or {}).items():
        gong = ent.get('gong', '')
        sihua[h] = '%s@%s(%s)' % (ent.get('star', ''), gong, tp.get(gong, ''))
    return {
        'layer_ming_zhi': ming,
        'layer_ming_xingxi': xingxi,
        'sihua': sihua,
        'double_hua': [],
        'shengong_zhus': [],
    }


def _month_granularity(date_str):
    return '-'.join(date_str.split('-')[:2])


def _display(hit, cur_person):
    """注入显示口径：非当前命主自动脱敏（person→另一命主、text→category、日期截月）。"""
    if hit.get('person') == cur_person:
        return {'person': hit['person'], 'text': hit.get('text', ''),
                'date': hit.get('date', '')}
    return {'person': '另一命主', 'text': hit.get('category', ''),
            'date': _month_granularity(hit.get('date', ''))}


def _group_and_stats(hits, cur_person):
    """分组：自身（一级）/跨命主（二级）；各组的预测次数与准确率。
    返回 (self_hits, cross_hits, stats)——stats={'self': (n_pred, n_acc), 'cross': (...)}。"""
    self_hits = [h for h in hits if h.get('person') == cur_person]
    cross_hits = [h for h in hits if h.get('person') != cur_person]

    def stat(group):
        preds = [h for h in group if h.get('verify_result') in (PRED_OK, PRED_BAD)]
        n_acc = sum(1 for h in preds if h['verify_result'] == PRED_OK)
        return len(preds), n_acc

    return self_hits, cross_hits, {'self': stat(self_hits), 'cross': stat(cross_hits)}


def _acc_text(n_pred, n_acc):
    """准确率行（口径）：n<5 样本不足；n≥5 出准确率。"""
    if n_pred < 5:
        return '样本不足暂不出准确率' if n_pred else '无预测数据'
    return '历史预测 %d 次，准确率 %d%%' % (n_pred, round(100.0 * n_acc / n_pred))


def _theory_line(h):
    """分析过程行：theory 非空展示完整推理链，空标历史无分析过程。"""
    theory = (h.get('theory') or '').strip()
    if theory:
        return '    分析过程：%s\n' % theory
    return '    （历史记录无分析过程）\n'


def _chain_line(h):
    """抽象经验链：配置+预测+结果——不注入原始事件叙事（无个人细节）。"""
    parts = []
    if h.get('prediction'):
        parts.append('预测"%s"' % h['prediction'])
    if h.get('outcome'):
        parts.append('实际%s' % h['outcome'])
    if h.get('verify_result') in (PRED_OK, PRED_BAD):
        parts.append('（%s）' % h['verify_result'])
    elif h.get('verify_result') and h['verify_result'] != '待验':
        parts.append('（%s）' % h['verify_result'])
    else:
        parts.append('（待验证）')
    return ' → '.join(parts) if parts else '（无预测数据——事件参考：%s）' % h.get('category', '')


REVISE_LINE = ('请对本节历史参考表态：采信/部分采信/反驳+一句理由，'
               '写入本宫 output 末尾『参考表态』段\n')
BAN_FANJI_LINE = '禁反象推断（如忌亏→禄赚）；反象样本仅入库各自攒数。\n'


def _grade(recs):
    """证据分级：一等=prediction 非空且 verify_result∈{预测准确,预测不准}；二等=其余。"""
    first = [r for r in recs
             if r.get('prediction') and r.get('verify_result') in (PRED_OK, PRED_BAD)]
    return first, [r for r in recs if r not in first]


def _grade_text(recs):
    """分级表述：n<5 不出比率（_acc_text 口径）。"""
    first, _ = _grade(recs)
    n_acc = sum(1 for r in first if r['verify_result'] == PRED_OK)
    return '一等证据（预测验证）%d 条（%s）/二等证据（事件关联）%d 条' % (
        len(first), _acc_text(len(first), n_acc), len(recs) - len(first))


def _liuyue_note(hit, cur_label):
    """L1 流月背景标注：记录农历月 vs 查询盘农历月。"""
    lab = hit.get('liuyue_label', '')
    if lab and cur_label and lab == cur_label:
        return '「完整同构」'
    return '「事象层同构，基调层（流月）不同」'


def _render_l1(recs, cur_person, cur_label):
    """盘型级印证节（干支直查制：全盘指纹等值/同干支整盘重现；分组保留：
    自身一级/跨命主二级）；recs 含 liuyue_label 字段。"""
    self_recs = [r for r in recs if r.get('person') == cur_person]
    cross_recs = [r for r in recs if r.get('person') != cur_person]
    section = ['【盘型级印证·历史印证参考】（盘型级匹配：同命主同盘型的历史经验链——'
               '配置+预测+结果；历史参考而非本日预测的验证，禁标"已实证"）\n']
    if self_recs:
        section.append('- 自身印证 %d 次（%s）：\n' % (len(self_recs), _grade_text(self_recs)))
        for r in self_recs[:5]:
            section.append('  - %s %s %s\n' % (r['date'], _chain_line(r),
                                               _liuyue_note(r, cur_label)))
            section.append(_theory_line(r))
    if cross_recs:
        section.append('- 跨命主参考 %d 次（%s）：\n' % (len(cross_recs), _grade_text(cross_recs)))
        for r in cross_recs[:5]:
            section.append('  - %s %s\n' % (r['date'], _chain_line(r)))
            section.append(_theory_line(r))
    if (self_recs and cross_recs
            and any(r['verify_result'] == PRED_OK for r in self_recs)
            and any(r['verify_result'] == PRED_OK for r in cross_recs)
            and not any(r['verify_result'] == PRED_BAD for r in self_recs + cross_recs)):
        section.append('- 上述自身与跨命主两独立来源对同配置结论一致=加强印证\n')
    section.append('提示：以上均为历史参考（历史经验，非本日预测的验证）——'
                   '本日事件的实际结果须事后由用户反馈，禁标"已实证"。\n')
    return section


def _render_layered(label, recs, cur_person):
    """星系级/宫位级参考节（干支直查制等值命中即注入，证据分级表述）。
    星系级=同干异支·应验宫同地支（结构跨宫迁移，参考级）；
    宫位级=同支异干·同宫名（宫位底色倾向，参考级——禁"应验"）。"""
    desc = ('星系级·同流日天干×异日支×应验宫同地支——同款四化+星系跨宫迁移，'
            if label.startswith('星系级')
            else '宫位级·同流日地支×异日干×同宫名——盘面排布全同仅四化不同，宫位底色倾向')
    section = ['【%s】（干支直查：%s；历史参考，非本日预测的验证）\n' % (label, desc)]
    section.append('- 此结构历史 %d 次（%s）：\n' % (len(recs), _grade_text(recs)))
    for r in recs[:5]:
        section.append('  - %s %s\n' % (r['date'], _chain_line(r)))
        section.append(_theory_line(r))
    section.append('提示：以上均为历史参考——禁标"已实证"。\n')
    return section


def inject_verify_refs(outdir, combo_features, cur_person, exclude_date=None,
                       data_dir=None, layer=None, structure_snapshot=None,
                       liuyue_label=None):
    """一查多注主入口（干支直查制 v2.0 三层互斥）：
    盘型级（全盘指纹等值+同干支整盘重现）+ 星系级（同干异支·应验宫同地支）+
    宫位级（同支异干·同宫名）注入，闸门 GATE=1；FAISS 兜底**撤注入权**
    ——fuzzy 命中只落 verify_refs.json 留档（match=fuzzy），不进任何 input_*.md。
    structure_snapshot=查询盘结构快照（liupan 侧同源生成）；缺省或分析日非完整日期
    （流月/流年层）则三层直查跳过。失败容错=警告+空清单。注入标注"历史参考"——禁标"已实证"。"""
    layer = layer if layer in ('liuri', 'liuyue', 'liunian', 'liushi') else None  # 结构化路径白名单含 liushi（向量路径不扩）
    refs_path = os.path.join(outdir, 'verify_refs.json')
    l1_hits, fuzzy_hits = [], []
    layered = {'panxing': [], 'xingxi': [], 'gongwei': []}
    try:
        l1_hits = structured_query(combo_features, cur_person, exclude_date=exclude_date,
                                   data_dir=data_dir, layer=layer)
        if not l1_hits:
            # 兜底：FAISS 向量相似度——仅留档备查，撤注入权（F1）
            fuzzy_hits = query_verify_refs(combo_features, exclude_date=exclude_date,
                                           data_dir=data_dir, layer=layer)
        if structure_snapshot:
            layered = layered_query(structure_snapshot, exclude_date=exclude_date,
                                    data_dir=data_dir)
    except (RuntimeError, ValueError, OSError, AttributeError, TypeError,
            subprocess.TimeoutExpired) as e:
        print('⚠ 历史印证查询失败（%s）——本批次不注入' % e)

    # 宫名 → [记录...] 注入块；layered 记录沿用经验链字段
    by_palace = {}
    records = []

    def route(hit, palaces, layer_tag, match, inject=True):
        disp = _display(hit, cur_person)
        records.append({
            'event_id': hit.get('event_id', ''), 'person': disp['person'],
            'category': hit.get('category', ''), 'date': disp['date'],
            'similarity': hit.get('similarity'), 'verify_result': hit.get('verify_result', ''),
            'prediction': hit.get('prediction', ''), 'outcome': hit.get('outcome', ''),
            'theory': hit.get('theory', ''),
            'text': disp['text'], 'routed_palaces': list(palaces),
            'match': match, 'layer': layer_tag,
            'liuyue_label': hit.get('liuyue_label', ''),
        })
        if inject:  # fuzzy 撤注入权：只留档 records，不进 by_palace
            for p in palaces:
                by_palace.setdefault(p, []).append(records[-1])

    # 盘型级=全盘指纹（structured_query）+同干支整盘重现（layered.panxing），event_id 去重
    seen_ids = set()
    for hit in l1_hits + layered['panxing']:
        eid = hit.get('event_id', '')
        if eid and eid in seen_ids:
            continue
        if eid:
            seen_ids.add(eid)
        palaces = CATEGORY_PALACES.get(hit.get('category', ''), [])
        if palaces:
            route(hit, palaces, '盘型级', 'structured')
    for hit in fuzzy_hits:  # fuzzy 只留档，撤注入权（F1）
        palaces = CATEGORY_PALACES.get(hit.get('category', ''), [])
        route(hit, palaces, '', 'fuzzy', inject=False)
    snapshot_palaces = ((structure_snapshot or {}).get('palaces') or {})
    for hit in layered['xingxi']:  # 星系级：今日同地支的全部宫
        palaces = [p for p, info in snapshot_palaces.items()
                   if info.get('zhi') == hit.get('_palace_zhi')]
        route(hit, palaces, '星系级', 'structured')
    for hit in layered['gongwei']:  # 宫位级：同宫名
        ep = hit.get('_palace', '')
        route(hit, [ep] if ep in snapshot_palaces else [], '宫位级', 'structured')

    with open(refs_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(records, f, ensure_ascii=False, indent=1)

    if not by_palace:
        print('历史印证：无注入命中（盘型级/星系级/宫位级均无；fuzzy 仅留档 %d 条）' % len(fuzzy_hits))
        return records

    for path in glob.glob(os.path.join(outdir, 'input_*.md')):
        m = INPUT_RE.match(os.path.basename(path))
        if not m or m.group(1) not in by_palace:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        recs = by_palace[m.group(1)]
        section = []
        n_pan = len([r for r in recs if r['layer'] == '盘型级'])
        n_xx = len([r for r in recs if r['layer'] == '星系级'])
        n_gw = len([r for r in recs if r['layer'] == '宫位级'])
        if n_pan:
            section += _render_l1([r for r in recs if r['layer'] == '盘型级'],
                                  cur_person, liuyue_label)
        if n_xx:
            section += _render_layered('星系级参考',
                                       [r for r in recs if r['layer'] == '星系级'], cur_person)
        if n_gw:
            section += _render_layered('宫位级参考',
                                       [r for r in recs if r['layer'] == '宫位级'], cur_person)
        if not section:
            continue  # 无三层内容=无注入（fuzzy 已撤权，不落任何痕迹）
        section.append(BAN_FANJI_LINE)
        section.append(REVISE_LINE)
        kb_at = next((j for j, ln in enumerate(lines) if '【知识库·' in ln), None)
        at = kb_at if kb_at is not None else len(lines)
        lines[at:at] = ['\n'] + section
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(lines)
        print('历史印证注入：%s（盘型级 %d / 星系级 %d / 宫位级 %d）'
              % (os.path.basename(path), n_pan, n_xx, n_gw))
    return records
