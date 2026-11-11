#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""简报质量闸门：全项检查（五节+往事为鉴常驻/每宫字数/综述字数/禁用符号/总字数/
经典双栏/经典引用格式/宜忌双层/预测行(liuri/liushi)/往事为鉴禁模式；往事为鉴两段叙事式定稿：
两段形态（首遇行 vs 命中尾注行）/节位次（综述后宜忌前）/节级预算[节总≤600]）。
节名体系：义理综述/往事为鉴/今日宜忌/逐宫推演/今日经典/今日典故；旧名不追溯。
用法: python check_brief.py <简报.md> [--type liuri|yuanju|daxian|liunian|liuyue|liushi]
exit=0 全PASS / exit=1 有FAIL
"""
import sys
import re
import argparse

SECTION_TEMPLATES = {
    "liuri": ["义理综述", "往事为鉴", "今日宜忌", "逐宫推演", "今日经典", "今日典故"],
    "yuanju": ["义理综述", "往事为鉴", "人生大宜忌", "逐宫推演", "终身经典", "终身典故"],
    "daxian": ["义理综述", "往事为鉴", "阶段宜忌", "逐宫推演", "阶段经典", "阶段典故"],
    "liunian": ["义理综述", "往事为鉴", "年度宜忌", "逐宫推演", "年度经典", "年度典故"],
    "liuyue": ["义理综述", "往事为鉴", "月度宜忌", "逐宫推演", "月度经典", "月度典故"],
    "liushi": ["义理综述", "往事为鉴", "时辰宜忌", "逐宫推演", "时辰经典", "时辰典故"],
}

FIRST_ENCOUNTER_LINE = "今日盘面，旧案无同款——首遇之局，以义理为准。"

BANNED = ["⭐", "⚠️", "✅", "❌", "🔴", "🟢"]

# 全层字数区间（上下限均检）：{层: {palace/overview/total: (下限, 上限)}}
LAYER_RANGES = {
    "yuanju": {"palace": (150, 300), "overview": (400, 600), "total": (4000, 6000)},
    "daxian": {"palace": (150, 300), "overview": (400, 600), "total": (4000, 6000)},
    "liunian": {"palace": (150, 250), "overview": (350, 500), "total": (4000, 5500)},
    "liuyue": {"palace": (150, 250), "overview": (300, 450), "total": (3500, 5000)},
    "liuri": {"palace": (120, 250), "overview": (250, 400), "total": (2500, 4000)},
    "liushi": {"palace": (80, 180), "overview": (150, 300), "total": (1200, 2500)},
}

PALACE_RE = re.compile(r"^\*\*(.{1,6}宫|身宫)\*\*[　\s]")

# 预测行双格式：旧「预测：」＋置信标注版「预测（高/中/低）：」（brief_prompt_template 硬性要求22 五层统一）
PRED_RE = re.compile(r"预测（[高中低]）：|预测：")


def cn_len(text):
    return len(re.sub(r"\s", "", text))


def split_sections(lines):
    """按 ## 节标题切分，返回 [(节名, [行])]；无 # 前导的内容归首（None）。"""
    secs = []
    cur_name, cur = None, []
    for line in lines:
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if cur_name is not None or cur:
                secs.append((cur_name, cur))
            cur_name, cur = m.group(1).strip(), []
        else:
            cur.append(line)
    secs.append((cur_name, cur))
    return secs


def find_section(secs, name):
    for sec_name, sec_lines in secs:
        if sec_name and name in sec_name:
            return sec_lines
    return None


def check_palaces(secs):
    """解析逐宫推演节内 **宫名**　段落，逐宫字数。"""
    sec = find_section(secs, "逐宫推演")
    if sec is None:
        return None, "缺逐宫推演节"
    palaces = []
    cur_name, cur = None, None
    for line in sec:
        m = PALACE_RE.match(line)
        if m:
            if cur_name is not None:
                palaces.append((cur_name, cn_len("".join(cur))))
            cur_name, cur = m.group(1), [line[m.end():]]
        elif cur_name is not None:
            cur.append(line)
    if cur_name is not None:
        palaces.append((cur_name, cn_len("".join(cur))))
    return palaces, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--type", default="liuri", choices=list(SECTION_TEMPLATES))
    ap.add_argument("--expect-tail", type=int, default=None, metavar="N",
                    help="昨日待验证条数：N>0=简报必须含「## 待验预测」节且正文实数=N（纯计数，标题不带计数）；N=0/不传=尾节可缺合法")
    args = ap.parse_args()

    with open(args.brief, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    secs = split_sections(lines)

    results = []  # (bool, 消息)

    # 1 五节存在（往事为鉴常驻：在且内容二选一=经验条目或固定首遇行）
    missing = [n for n in SECTION_TEMPLATES[args.type] if find_section(secs, n) is None]
    wjj = find_section(secs, "往事为鉴")
    wjj_ok = wjj is not None and (any(ln.strip() for ln in wjj))
    if wjj is not None and wjj_ok and FIRST_ENCOUNTER_LINE not in "".join(wjj) \
            and "本节参考" not in "".join(wjj) \
            and not any("次" in ln or "应验" in ln for ln in wjj):
        wjj_ok = False  # 有内容但既无首遇行也无命中尾注/经验条目迹象
    msg1 = "节1 五节齐（含往事为鉴常驻）"
    if missing:
        msg1 += f" [缺{'/'.join(missing)}节]"
    if not wjj_ok:
        msg1 += " [往事为鉴节缺失或为空]"
    results.append((not missing and wjj_ok, msg1))

    rng = LAYER_RANGES[args.type]

    # 2 每宫字数（全层上下限均检）
    lo_p, hi_p = rng["palace"]
    palaces, err = check_palaces(secs)
    if err:
        results.append((False, f"节2 每宫字数 [{err}]"))
    else:
        fails = [f"{n}({c}字)" for n, c in palaces
                 if n != "身宫"
                 and (c < lo_p or (hi_p is not None and c > hi_p))]
        # yuanju 检测身宫第13段（**身宫**　≥120字，独立于十二宫下限）
        if args.type == "yuanju":
            sg = next(((n, c) for n, c in palaces if n == "身宫"), None)
            if sg is None:
                fails.append("身宫段缺失")
            elif sg[1] < 120:
                fails.append(f"身宫({sg[1]}字<120)")
        msg = f"节2 每宫字数 [{lo_p}-{hi_p}]"
        if fails:
            msg += f" [FAIL: {' '.join(fails)}]"
        elif not palaces:
            msg += " [FAIL: 未解析到宫段落]"
            fails = ["none"]
        results.append((not fails, msg))

    # 3 综述字数（义理综述；全层上下限均检；综述末「一句话」主打诀行不计——金句配额独立于综述正文）
    lo_o, hi_o = rng["overview"]
    ov = find_section(secs, "义理综述")
    ov_len = cn_len("".join(ln for ln in (ov or []) if not ln.lstrip().startswith("一句话")))
    ok3 = ov_len >= lo_o and (hi_o is None or ov_len <= hi_o)
    results.append((ok3, f"节3 综述字数 ({ov_len}字)"))
    # 3b 综述分段硬闸：各段+主打诀行之间必须空行分隔（四行连续无空行形态）
    ov_miss3b = []
    if ov and len(ov) >= 2:
        ov_nonblank = [l for l in ov if l.strip()]
        if len(ov_nonblank) >= 2:
            for _i in range(len(ov) - 1):
                if ov[_i].strip() and ov[_i + 1].strip():
                    # 两行都有内容但紧挨（无空行）
                    if not ov[_i + 1].lstrip().startswith("一句话") or True:
                        ov_miss3b.append("综述段间缺空行分隔")
                        break
    results.append((not ov_miss3b, "节3b 综述分段" + ("" if not ov_miss3b else " [" + "；".join(ov_miss3b) + "]")))

    # 4 禁用符号
    hits = {s: text.count(s) for s in BANNED if s in text}
    results.append((not hits, "节4 禁用符号" + (f" [发现: {' '.join(f'{k}×{v}' for k, v in hits.items())}]" if hits else "")))

    # 5 总字数（全层上下限均检；「待验预测」尾节与「近期事件」节均为动态追加，不计入主体字数预算）
    lo_t, hi_t = rng["total"]
    TAIL = "待验预测"
    DRAFT = "近期事件"
    body_lines = [ln for n, sec in secs if not (n and (TAIL in n or n.startswith(DRAFT))) for ln in sec]
    total = cn_len("\n".join(body_lines))
    results.append((lo_t <= total <= hi_t, f"节5 总字数 ({total}字)"))

    # 6 经典双栏
    has_jd = find_section(secs, "经典") is not None
    has_dg = find_section(secs, "典故") is not None
    results.append((has_jd and has_dg, "节6 经典双栏"))

    # 7 经典/典故引用格式二合一（引用块/来源标注；验证工序保留在派单硬性要求，产物不再要求标注）
    miss7 = []
    for sec_name in ("经典", "典故"):
        sec = find_section(secs, sec_name)
        if sec is None:
            continue
        quote_idx = [i for i, ln in enumerate(sec) if ln.startswith("> **")]
        if not quote_idx:
            miss7.append(f"{sec_name}缺引用块(> **)")
            continue
        ok_src = any("——《" in sec[i] for i in quote_idx)
        if not ok_src:
            miss7.append(f"{sec_name}缺来源标注(——《")
    results.append((not miss7, "节7 经典引用格式" + ("" if not miss7 else " [" + "；".join(miss7) + "]")))

    # 8 宜忌双层结构（全层）：主题块首=加粗主题行（非动作行），块内须含≥1行加粗 **宜：/**忌： 动作行
    yj = find_section(secs, "宜忌")
    topic_re = re.compile(r"^\*\*[^*]+\*\*")
    act_re = re.compile(r"^\*\*(宜|忌)：")
    ok8, miss8 = True, []
    if yj is None:
        ok8, miss8 = False, ["缺宜忌节"]
    else:
        topics = [(i, ln) for i, ln in enumerate(yj) if topic_re.match(ln) and not act_re.match(ln)]
        if not topics:
            ok8, miss8 = False, ["未发现主题行(加粗编号+主题词)"]
        else:
            for j, (i, ln) in enumerate(topics):
                end = topics[j + 1][0] if j + 1 < len(topics) else len(yj)
                if not any(act_re.match(x) for x in yj[i + 1:end]):
                    ok8 = False
                    miss8.append(f"主题块「{ln.strip('*')[:12]}」缺**宜：/**忌：动作行")
    results.append((ok8, "节8 宜忌双层" + ("" if ok8 else " [" + "；".join(miss8) + "]")))

    # 9 liuri/liushi 层宜忌节须≥1行含「预测：」（防追踪断粮）
    if args.type in ("liuri", "liushi"):
        ok9 = yj is not None and any(PRED_RE.search(ln) for ln in yj)
        results.append((ok9, "节9 %s 预测行" % ("liuri" if args.type == "liuri" else "liushi")
                        + ("" if ok9 else " [宜忌节无「预测：」行]")))

    # 10 往事为鉴禁模式（全层）：禁裸小数相似度、禁「参考 0 次」
    miss10 = []
    if wjj is not None:
        wjj_text = "".join(wjj)
        if re.search(r"0\.\d{2}", wjj_text):
            miss10.append("含裸小数相似度")
        if "参考 0 次" in wjj_text or "参考0次" in wjj_text:
            miss10.append("含「参考 0 次」")
    results.append((not miss10, "节10 往事为鉴禁模式" + ("" if not miss10 else " [" + "；".join(miss10) + "]")))

    # 11 往事为鉴形态合法性与位次（两段叙事式）：
    # 有命中=节内须含尾注行（「（本节参考」前缀且含至少一个日期）；无命中=固定首遇行；两形态互斥。
    # 节位次：须在义理综述之后、宜忌之前。
    DATE_RE = re.compile(r"\d{4}[-/.年]\d{1,2}")
    miss11 = []
    wjj_paras = []
    wjj_lines = []
    wjj_text = ""
    if wjj is not None:
        wjj_text = "\n".join(wjj)
        wjj_lines = [ln.strip() for ln in wjj if ln.strip()]
        wjj_paras = [p.strip() for p in re.split(r"\n\s*\n", wjj_text) if p.strip()]
        has_first = any(FIRST_ENCOUNTER_LINE in ln for ln in wjj_lines)
        tail_lines = [ln for ln in wjj_lines if ln.startswith("（本节参考")]
        has_hit = bool(tail_lines)
        if has_first and has_hit:
            miss11.append("首遇行与命中尾注并存（互斥违规）")
        if not has_first and not has_hit:
            miss11.append("既无首遇行也无命中尾注行")
        elif has_hit and not any(DATE_RE.search(ln) for ln in tail_lines):
            miss11.append("尾注行缺日期")
        # 节位次：综述后、宜忌前
        named_secs = [n for n, _ in secs if n]
        if "往事为鉴" in named_secs and len(named_secs) >= 3:
            i_wjj = named_secs.index("往事为鉴")
            i_ov = named_secs.index("义理综述") if "义理综述" in named_secs else -1
            i_yj = next((i for i, n in enumerate(named_secs) if "宜忌" in n), len(named_secs))
            if not (i_ov < i_wjj < i_yj):
                miss11.append("位次违规（须在义理综述之后、宜忌之前）")
        # 象别版本名禁入简报（保留）
        ver = [w for w in ("得助版", "受伤版", "L1", "L2", "L3", "盘型级", "星系级", "宫位级") if w in wjj_text]
    # 尾注格式硬闸：及义理后禁带书名/出处
    import re as _re
    _tail = _re.search(r'及义理(.{0,20})', wjj_text)
    if _tail and _tail.group(1).startswith('·'):
        miss11.append(f"尾注「及义理」后禁带出处：发现「及义理{_tail.group(1)[:10]}」——应写「及义理）")
    # 分段硬闸：第一段/第二段/尾注之间必须空行分隔
    _wjj_lines = [l for l in wjj_text.split(chr(10)) if l.strip()]
    if len(_wjj_lines) >= 2:
        for _i in range(len(_wjj_lines) - 1):
            _cur_end = wjj_text.find(_wjj_lines[_i]) + len(_wjj_lines[_i])
            _next_start = wjj_text.find(_wjj_lines[_i + 1])
            if _next_start - _cur_end < 2:  # 无空行（只换行没空行）
                miss11.append(f"往事为鉴段{_i+1}与段{_i+2}之间缺空行分隔（Markdown 段落要求）")
                break
        if ver:
            miss11.append("含工程/象别版本名：%s" % "、".join(sorted(set(ver))))
    results.append((not miss11, "节11 往事为鉴两段形态/位次" + ("" if not miss11 else " [" + "；".join(miss11) + "]")))

    # 12 L3 星系背景段措辞边界（性质参考级）：禁"应验"（"若应验"除外）/禁置信词/须计数括注
    miss12 = []
    if wjj_paras:
        l3_paras = [p for p in wjj_paras if "星系背景" in p or "星系旧例" in p]
        for p in l3_paras:
            bad = re.findall(r"(?<!若)应验", p)
            if bad:
                miss12.append("L3 段含结论级措辞「应验」")
            conf = [w for w in ("高置信", "中置信", "低置信", "准确率") if w in p]
            if conf:
                miss12.append("L3 段含置信词：%s" % "、".join(sorted(set(conf))))
            if not re.search(r"（星系背景[^）]*条", p):
                miss12.append("L3 段缺计数括注「（星系背景 N 条…）」")
    results.append((not miss12, "节12 L3 段措辞边界" + ("" if not miss12 else " [" + "；".join(miss12) + "]")))

    # 13 往事为鉴节级字数预算（两段叙事式）：节总 ≤600 中文字符（去空白）；
    # 首遇行节不检；有命中时另查尾注行存在（缺=FAIL）。
    miss13 = []
    if wjj_lines:
        has_first13 = any(FIRST_ENCOUNTER_LINE in ln for ln in wjj_lines)
        has_hit13 = any(ln.startswith("（本节参考") for ln in wjj_lines)
        if has_hit13 and not any(DATE_RE.search(ln) for ln in wjj_lines if ln.startswith("（本节参考")):
            miss13.append("尾注行缺日期")
        if not has_first13:
            total13 = cn_len("\n".join(wjj_lines))
            if total13 > 600:
                miss13.append(f"节总 {total13}字>600")
            if not has_hit13:
                miss13.append("有命中内容但缺尾注行（「（本节参考…」）")
    results.append((not miss13, "节13 往事为鉴节级预算(节总≤600)" + ("" if not miss13 else " [" + "；".join(miss13) + "]")))

    # 14 尾节「待验预测」：liuri/liushi/liuyue/liunian 四层常驻必须（条目列表或空态句
    # 「上一批次无待验预测。」，位置=最末节「近期事件」之前）；yuanju/daxian 维持可缺豁免。
    named = [n for n, _ in secs if n]
    has_tail = any(TAIL in n for n in named)
    TAIL_REQUIRED = args.type in ("liuri", "liushi", "liuyue", "liunian")
    EMPTY_TAIL_LINE = "上一批次无待验预测。"
    miss14 = []
    extra = [n for n in named if TAIL not in n
             and not n.startswith("近期事件")
             and not any(t in n for t in SECTION_TEMPLATES[args.type])]
    if extra:
        miss14.append("多余节：%s" % "、".join(extra))
    # 尾节之后允许且仅允许「近期事件」开头节（自动扫描合法尾后节）
    if has_tail and named:
        after_tail = named[named.index(next(n for n in named if TAIL in n)) + 1:]
        if any(not n.startswith("近期事件") for n in after_tail):
            miss14.append("尾节「%s」未置最末（之后仅允许近期事件节）" % TAIL)
    if has_tail:
        tail_lines = secs[next(i for i, (n, _) in enumerate(secs) if n and TAIL in n)][1]
        tail_n = sum(1 for ln in tail_lines if ln.strip())
        # 标题不带计数（旧标题括注比对废弃），expect_tail 纯计数主判
        if args.expect_tail is not None and args.expect_tail > 0 and tail_n != args.expect_tail:
            miss14.append("应有尾节 %d 条但条数不符（正文实数 %d 条）" % (args.expect_tail, tail_n))
    if args.expect_tail is not None and args.expect_tail > 0 and not has_tail:
        miss14.append("应有尾节 %d 条但缺失" % args.expect_tail)
    # 四层常驻闸：尾节缺失=FAIL；存在但既无条目也无空态句=FAIL（expect_tail>0 条数校验见上，逻辑不变）
    if TAIL_REQUIRED and not has_tail:
        miss14.append("缺尾节「待验预测」（%s 层常驻必须，无条目须写空态句「%s」）" % (args.type, EMPTY_TAIL_LINE))
    if TAIL_REQUIRED and has_tail:
        tail_lines_all = secs[next(i for i, (n, _) in enumerate(secs) if n and TAIL in n)][1]
        if not any(ln.strip() for ln in tail_lines_all) or (
                not any(ln.strip() for ln in tail_lines_all if ln.strip() != EMPTY_TAIL_LINE)
                and not any(EMPTY_TAIL_LINE in ln for ln in tail_lines_all)):
            miss14.append("尾节既无条目也无空态句「%s」" % EMPTY_TAIL_LINE)
    if TAIL_REQUIRED:
        label14 = "节14 尾节必备(%s)" % args.type
    elif args.expect_tail is not None and args.expect_tail > 0:
        label14 = "节14 尾节必备(%d 条)" % args.expect_tail
    else:
        label14 = "节14 尾节豁免(可缺/可在末)"
    results.append((not miss14, label14 + ("" if not miss14 else " [" + "；".join(miss14) + "]")))

    # 15 财务方向句（可选）：命主有投资场景才出，不强制
    if args.type in ("__none__",):
        cond_re = re.compile(r"若|如果|一旦")
        trade_re = re.compile(r"期货|股票|长线|短线|盘面|仓位|账面|收益|盈亏|杠杆|端")
        pred_lines = [ln for ln in (yj or []) if PRED_RE.search(ln)]
        has_dir = any(not cond_re.search(ln) and trade_re.search(ln) for ln in pred_lines)
        layer_tag = {"liuri": "交易块", "liuyue": "月度方向句", "liunian": "年度方向句", "liushi": "时辰方向句"}[args.type]
        results.append((has_dir, "节15 方向句存在" + (f"[{layer_tag}≥1条]" if has_dir
                       else f" [宜忌节缺方向句预测行——按 brief_prompt_template {layer_tag}并存口径补一条无条件从句的方向句]")))
    else:
        results.append((True, "节15 豁免(该层无方向句要求)"))

    for ok, msg in results:
        print(("PASS " if ok else "FAIL ") + msg)
    all_pass = all(ok for ok, _ in results)
    print("总体: " + ("PASS" if all_pass else "FAIL"))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
