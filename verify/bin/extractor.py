# -*- coding: utf-8 -*-
"""盘侧特征回填：对账本中 combo_features 为空的事件行，按命主盘+事件日期
调 core/liupan.py 确定性重算流盘特征，行对行原位替换回填（不动行数、event_id、theory）。
另支持 --set-theory 原位更新单行 theory 字段。零第三方依赖。

用法：
extractor.py [--data-dir 目录] [--event-id <id> ...]        # 回填 combo_features（缺省全量扫，非空跳过）
extractor.py --rebuild-all [--data-dir 目录]                # 清空所有 combo_features 后全量强制重算（方法论修正后刷新）
extractor.py --set-theory <id> "<文本>" [--data-dir 目录]    # 原位更新该行 theory
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import list_shards, out, resolve_data_dir, resolve_event_palace

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(BIN_DIR))  # verify\bin -> ziwei-analyze
LIUPAN = os.path.join(SKILL_ROOT, "core", "liupan.py")
PANS_DIR = os.path.join(SKILL_ROOT, "pans")

BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
MAIN14 = {"紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴",
          "贪狼", "巨门", "天相", "天梁", "七杀", "破军"}

# 事件 level -> (liupan 层名, 日期参数名)；level 为空时按 date_precision 定
LEVEL_MAP = {
    "流日": ("liuri", "--date"), "流月": ("liuyue", "--month"), "流年": ("liunian", "--year"),
    "liuri": ("liuri", "--date"), "liuyue": ("liuyue", "--month"), "liunian": ("liunian", "--year"),
    "liushi": ("liushi", "--date"),  # 时支后缀拆参后另传 --hour（level_args 处理）
}
PRECISION_MAP = {"day": "流日", "month": "流月", "year": "流年", "hour": "流时"}


def opposite(zhi):
    return BRANCHES[(BRANCHES.index(zhi) + 6) % 12]


def load_pan(person):
    path = os.path.join(PANS_DIR, person + ".json")
    if not os.path.isfile(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("pan", {}), path


def run_liupan(pan_path, level_key, date_args):
    """date_args=[(参数名, 值), ...]（liushi 支=--date+--hour 双参）。"""
    cmd = [sys.executable, LIUPAN, "--pan", pan_path, "--level", level_key]
    for arg, val in date_args:
        cmd += [arg, val]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("liupan 失败: %s" % r.stderr.decode("utf-8", "replace").strip())
    text = r.stdout.decode("utf-8", "replace")
    obj, end = json.JSONDecoder().raw_decode(text)
    return obj, text[end:]


def parse_palace_table(md):
    """三层并标表 -> {宫名: {层名: (支, [星])}}；取事象层（第1数据列）与各层备用。"""
    rows = {}
    for line in md.splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| 宫名"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        name, layers = cells[0], []
        for c in cells[1:4]:
            if "·" in c:
                zhi, star_part = c.split("·", 1)
                stars = [s for s in re.split(r"[、,，]", star_part) if s]
            else:
                zhi, stars = "", []
            layers.append((zhi, stars))
        rows[name] = layers  # [事象层, 基调层, 本质层]
    return rows


def parse_sihua_land(md):
    """'上层四化落本层宫'节 -> {(星, 化象): 宫名}。"""
    land = {}
    sec = re.search(r"## 上层四化落本层宫[^\n]*\n(.*?)(?=\n## )", md, re.S)
    if not sec:
        return land
    for m in re.finditer(r"- (\S+?)化([禄权科忌]) → 落本层【(.+?)】", sec.group(1)):
        star = m.group(1)
        if star and star[-1] in BRANCHES:  # 星名后粘宫支（如"贪狼丑"）
            star = star[:-1]
        land[(star, m.group(2))] = m.group(3)
    return land


def parse_double_hua(md, land):
    """同星双化两节 -> ['双化禄@仆役', ...]（落宫经 land 表按星+化象查）。"""
    items = []
    for sec_pat in (r"## 同星双化（紧邻上层→本层）[^\n]*\n(.*?)(?=\n## )",
                    r"## 同星双化（流年→本层，化象参差）[^\n]*\n(.*?)(?=\n## )"):
        sec = re.search(sec_pat, md, re.S)
        if not sec:
            continue
        for m in re.finditer(r"- (\S+?)：.*?「(.+?)」", sec.group(1)):
            star, tag = m.group(1), m.group(2)
            gong = land.get((star, tag[-1]), "")
            items.append(tag + ("@" + gong if gong else ""))
    return items


def build_combo(pan, obj, md):
    palaces = obj.get("palaces", {})
    table = parse_palace_table(md)

    ming_zhi = obj.get("ming_zhi", "")
    layer_xingxi = ""
    ming_layers = table.get("命宫")
    if ming_layers:
        zhi, stars = ming_layers[0]
        main = [s for s in stars if s in MAIN14]
        minor = [s for s in stars if s not in MAIN14]
        if main:
            layer_xingxi = "".join(main)
        else:
            opp = table.get("迁移")
            if opp:
                o_zhi, o_stars = opp[0]
                o_main = [s for s in o_stars if s in MAIN14]
                if o_main:
                    layer_xingxi = "借" + "".join(o_main) + "(%s)" % o_zhi
        if minor and layer_xingxi:
            layer_xingxi += "+" + "".join(minor)
        elif minor:
            layer_xingxi = "".join(minor)

    sihua = {}
    for xiang, ent in obj.get("sihua", {}).items():
        gong = ent.get("gong", "")
        sihua[xiang] = "%s@%s(%s)" % (ent.get("star", ""), gong, palaces.get(gong, ""))

    land = parse_sihua_land(md)
    double_hua = parse_double_hua(md, land)

    # 身宫主星：流日层不分析身宫（liupan SHENGONG_NOTE），取原局身宫支的十四主星；
    # 无主星则借对宫主星（前缀"借"）。
    shengong_zhus = []
    ming_shen = pan.get("mingShen", {})
    shen_zhi = ming_shen.get("shen", "")
    star_map = pan.get("allStarMap", {})
    if shen_zhi:
        mains = [s for s, z in star_map.items() if z == shen_zhi and s in MAIN14]
        if mains:
            shengong_zhus = mains
        else:
            o = opposite(shen_zhi)
            shengong_zhus = ["借" + s for s, z in star_map.items() if z == o and s in MAIN14]

    return {
        "layer_ming_zhi": ming_zhi,
        "layer_ming_xingxi": layer_xingxi,
        "sihua": sihua,
        "double_hua": double_hua,
        "shengong_zhus": shengong_zhus,
    }


def build_structure_snapshot(pan, obj, md):
    """结构快照（盘侧同源生成，禁手填）：宫名→{xingxi 含借标/zhi/sihua_in
    （当日层四化照入该宫三方四正的 象@支 清单）/tai_sui/bo_shi}+顶层 liuyue_label。
    星系口径与 build_combo 同源（parse_palace_table 事象层）。"""
    table = parse_palace_table(md)
    # 支→宫名映射（借宫取对宫主星用）
    by_zhi = {}
    for name, layers in table.items():
        if layers and layers[0][0]:
            by_zhi[layers[0][0]] = name
    sihua = obj.get("sihua", {})
    gods = obj.get("twelve_gods") or {}
    liuyue_label = ""
    for ent in obj.get("chain", []) or []:
        if ent.get("level") == "liuyue":
            liuyue_label = ent.get("label", "")
    snap_palaces = {}
    for name, layers in table.items():
        if not layers:
            continue
        zhi, stars = layers[0]
        if not zhi:
            continue
        main = [s for s in stars if s in MAIN14]
        minor = [s for s in stars if s not in MAIN14]
        if main:
            xingxi = "".join(main)
        else:
            o_main = []
            opp = opposite(zhi)
            o_layers = table.get(by_zhi.get(opp, ""), [])
            if o_layers:
                o_main = [s for s in o_layers[0][1] if s in MAIN14]
            if o_main:
                xingxi = "借" + "".join(o_main) + "(%s)" % opp
            else:
                xingxi = ""
        if minor:
            xingxi = ("%s+" % xingxi if xingxi else "") + "".join(minor)
        if not xingxi:
            continue
        i = BRANCHES.index(zhi)
        sf4 = {zhi, opposite(zhi), BRANCHES[(i + 4) % 12], BRANCHES[(i + 8) % 12]}
        sihua_in = sorted("%s@%s" % (xiang, ent.get("gong", ""))
                          for xiang, ent in sihua.items()
                          if ent.get("gong", "") in sf4)
        snap_palaces[name] = {
            "xingxi": xingxi,
            "zhi": zhi,
            "sihua_in": sihua_in,
            "tai_sui": (gods.get("taiSuiTwelve", {}) or {}).get(zhi, ""),
            "bo_shi": (gods.get("boShi", {}) or {}).get(zhi, ""),
        }
    return {"liuyue_label": liuyue_label, "palaces": snap_palaces}


def iter_events(data_dir):
    """yield (path, line_idx, rec)；非法行跳过。"""
    for _, _, name in list_shards(data_dir):
        path = os.path.join(data_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            raw = f.readlines()
        for i, line in enumerate(raw):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            yield path, i, raw, rec


def rewrite_line(path, raw, idx, rec):
    raw[idx] = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(raw)


def level_args(rec):
    """按层取流盘参数。返回 (层名, [(参数名, 值), ...]) 或 None（无法定位流盘）。
    liushi=独立分支：要求 precision==hour+date 时支后缀形态，拆 --date+--hour 双参。"""
    level = rec.get("level") or PRECISION_MAP.get(rec.get("date_precision", ""), "")
    if level not in LEVEL_MAP:
        return None
    key, arg = LEVEL_MAP[level]
    date_val = rec.get("event_date", "")
    precision = rec.get("date_precision", "")
    if level == "liushi":
        if precision != "hour":
            return None  # 流时层须时精度（时支后缀形态）
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-([子丑寅卯辰巳午未申酉戌亥])$", date_val)
        if not m:
            return None
        return key, [("--date", m.group(1)), ("--hour", m.group(2))]
    if arg == "--date" and precision != "day":
        return None  # 流日层须日精度
    if arg == "--month" and precision not in ("day", "month"):
        return None
    if not date_val:
        return None
    if arg == "--month":
        date_val = "-".join(date_val.split("-")[:2])
    if arg == "--year":
        date_val = date_val[:4]  # liunian+day 组合截前 4 位（防 int 崩）
    return key, [(arg, date_val)]


def do_set_theory(data_dir, event_id, text):
    for path, i, raw, rec in iter_events(data_dir):
        if rec.get("event_id") == event_id:
            rec["theory"] = text
            rewrite_line(path, raw, i, rec)
            out("已更新 theory：%s（原位替换，行数不变）" % event_id)
            return True
    out("错误：未找到 event_id=%s" % event_id)
    return False


def do_backfill(data_dir, event_ids, rebuild_all=False):
    want = set(event_ids) if event_ids else None
    done = skipped = failed = 0
    seen = set()
    for path, i, raw, rec in iter_events(data_dir):
        eid = rec.get("event_id", "")
        if eid in seen:  # 同分片文件按行迭代中已 rewrite，防陈旧重复
            continue
        seen.add(eid)
        if want is not None and eid not in want:
            continue
        if rec.get("combo_features") and rec.get("structure_snapshot") and not rebuild_all:
            out("跳过（combo_features/structure_snapshot 已非空）：%s" % eid)
            skipped += 1
            continue
        if rebuild_all:
            rec["combo_features"] = {}  # 先清空，重算失败也不留旧版特征
            rec["structure_snapshot"] = {}
            rewrite_line(path, raw, i, rec)
        person = rec.get("person", "")
        pan, pan_path = load_pan(person)
        if pan is None:
            out("跳过（无盘文件 pans\\%s.json）：%s" % (person, eid))
            skipped += 1
            continue
        la = level_args(rec)
        if la is None:
            out("跳过（层级/日期精度无法定位流盘）：%s level=%r precision=%r"
                % (eid, rec.get("level"), rec.get("date_precision")))
            skipped += 1
            continue
        try:
            obj, md = run_liupan(pan_path, la[0], la[1])
            combo = build_combo(pan, obj, md)
            snap = build_structure_snapshot(pan, obj, md)
        except (RuntimeError, ValueError, KeyError) as e:
            out("FAIL（%s）：%s" % (eid, e))
            failed += 1
            continue
        rec["combo_features"] = combo
        if snap.get("palaces"):
            rec["structure_snapshot"] = snap
        rewrite_line(path, raw, i, rec)
        out("已回填：%s %s 命宫(%s) 双化%d条 快照%d宫"
            % (eid, la[0], combo["layer_ming_zhi"], len(combo["double_hua"]),
               len(snap.get("palaces", {}))))
        done += 1
    out("回填完成（%s）：%d 成功 / %d 跳过 / %d 失败"
        % ("rebuild-all 全量强制" if rebuild_all else "增量", done, skipped, failed))
    return failed == 0


def do_backfill_palace(data_dir):
    """存量回填 event_palace：读每条 theory ①段宫位判定→写 event_palace；
    已有 event_palace 的行跳过（幂等）；行内其余字段原样保留。跑毕输出人工核对清单。"""
    report = []
    for path, i, raw, rec in iter_events(data_dir):
        eid = rec.get("event_id", "")
        if rec.get("event_palace"):
            report.append((rec.get("person", ""), eid, rec.get("event_date", ""),
                           rec.get("event_palace", ""), "已有跳过", ""))
            continue
        palace, ambiguous, warn = resolve_event_palace(
            rec.get("category", ""), rec.get("theory", ""))
        if palace:
            rec["event_palace"] = palace
        if ambiguous:
            rec["palace_ambiguous"] = True
        rewrite_line(path, raw, i, rec)
        report.append((rec.get("person", ""), eid, rec.get("event_date", ""),
                       palace or "（无）", "已回填" if palace else "无判定",
                       "ambiguous" if ambiguous else ""))
        if warn:
            report.append((rec.get("person", ""), eid, rec.get("event_date", ""),
                           palace or "", "警告", warn))
    out("回填清单（person/event_id/date/提取宫名/状态/ambiguous）：")
    for row in report:
        out("  %s / %s / %s / %s / %s / %s" % row)
    out("回填完成：%d 条扫描" % len(report))
    return True


def main():
    ap = argparse.ArgumentParser(description="盘侧特征回填 combo_features / theory 原位更新")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--event-id", dest="event_id", action="append", default=None)
    ap.add_argument("--rebuild-all", dest="rebuild_all", action="store_true", default=False,
                    help="清空所有 combo_features 后全量强制重算（方法论修正后刷新）")
    ap.add_argument("--set-theory", dest="set_theory", nargs=2, metavar=("ID", "文本"), default=None)
    ap.add_argument("--backfill-palace", dest="backfill_palace", action="store_true",
                    default=False, help="存量回填 event_palace（theory ①段宫位判定提取）")
    args = ap.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    if args.set_theory:
        ok = do_set_theory(data_dir, args.set_theory[0], args.set_theory[1])
        sys.exit(0 if ok else 2)
    if args.backfill_palace:
        do_backfill_palace(data_dir)
        sys.exit(0)
    ok = do_backfill(data_dir, args.event_id or [], rebuild_all=args.rebuild_all)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
