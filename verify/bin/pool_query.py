#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pool_query — 按宫同型池查询（预判学习体系方案 v1.5 件 3 归因配套工具）。

查 <person> <palace> 宫在 <date>（当日基准日）的同型池：同日干 + 应验宫同支的
历史 events 条目 + 逐条判定（盈/亏方向 × 准确/不准）。与 pattern_stats
--with-pool-stats 同一匹配与统计口径（共用 pattern_stats 内函数，禁单侧改口径）。

用途：周检错题归因②（同型池 ≥2 同向错→结构偏）与晨链调档核查。

用法：
  PYTHONUTF8=1 python pool_query.py --person <person> --palace <宫名> --date 2026-11-20
输出：人类可读条目清单 + 分组统计行。
"""
import argparse
import json
import os
import sys

from common import list_shards, resolve_data_dir
from pattern_stats import build_pool_stats


def main():
    ap = argparse.ArgumentParser(description="按宫同型池查询（归因/调档共用）")
    ap.add_argument("--person", required=True, help="命主名")
    ap.add_argument("--palace", required=True, help="应验宫（现仅财帛）")
    ap.add_argument("--date", required=True, help="当日基准日 YYYY-MM-DD")
    ap.add_argument("--data-dir", default=None, help="events 数据目录（默认三级解析）")
    args = ap.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    shards = list_shards(data_dir, owner=args.person)
    if not shards:
        sys.exit("未找到命主 %s 的 events 分片（目录 %s）" % (args.person, data_dir))

    # 当日该宫地支：从当日 pan 文件读（pan['palaces']={支:宫名} 反查），缺则须手供
    palace_zhi = None
    pan_path = os.path.join(data_dir, "..", args.person, "Liuri", "temp", args.date,
                            "pan_liuri_%s.json" % args.date)
    if os.path.isfile(pan_path):
        with open(pan_path, encoding="utf-8") as f:
            palaces = json.load(f).get("palaces") or {}
        palace_zhi = next((zhi for zhi, name in palaces.items()
                           if name == args.palace), None)
    if not palace_zhi:
        sys.exit("当日 %s 宫地支未取到（pan 文件缺：%s）——请补 pan 或改用 "
                 "pattern_stats --with-pool-stats 显式传 --palace-zhi" % (args.palace, pan_path))

    pool = build_pool_stats(data_dir, shards, args.palace, palace_zhi, args.date)
    print("同型池：%s宫 应验宫%s支 · 当日%s（同日干=%s）"
          % (args.palace, palace_zhi, args.date, pool["stats"]["day_ganzhi"]))
    for e in pool["entries"]:
        judge = "—" if e["judged"] is None else ("准确" if e["judged"] else "不准")
        print("  %s %s %s宫%s %s → %s向 %s"
              % (e["date"], e["day_ganzhi"], e["palace"], e["palace_zhi"],
                 e["xingxi"], e["direction"] or "?", judge))
    print(pool["injection_text"])


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
