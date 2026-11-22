#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交易日历联网更新器（a_stock 列）。

数据源：akshare 新浪交易日历（免费无 key）——按日期对齐更新 a_stock 列；
futures/interbank 列保留原值不动（两市场与 A 股开市差异日每年仅数天，静态预置即可）。
写回 data/trade_calendar.csv（保持三列结构、按 date 排序）。

退出码：0=成功（或无变更）；1=网络/数据失败（保留旧表）；2=akshare 未安装。
  akshare 缺席提示 pip install akshare。
  --dry-run 只显示会变更的行数，不写回。
禁读 .env。PYTHONUTF8=1 兼容。
"""
import argparse
import csv
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CALENDAR = os.path.normpath(os.path.join(HERE, "..", "data", "trade_calendar.csv"))
COLUMNS = ["date", "a_stock", "futures", "interbank"]


def main():
    ap = argparse.ArgumentParser(description="交易日历 a_stock 列联网更新（akshare/新浪）")
    ap.add_argument("--dry-run", action="store_true", help="只显示会变更的行数，不写回")
    args = ap.parse_args()

    try:
        import akshare as ak
    except ImportError:
        sys.stderr.write("akshare 未安装——pip install akshare 后重试。\n")
        return 2

    try:
        # 旧名 tool_trade_date_hist_sina 已在 akshare 1.20.45 更名，两代 API 兼容
        fn = getattr(ak, "calendar_trade_date_hist_sina", None) or ak.tool_trade_date_hist_sina
        df = fn()
    except Exception as e:
        sys.stderr.write("交易日历拉取失败（网络/数据源）：%s——保留旧表。\n" % e)
        return 1
    try:
        col = "trade_date" if "trade_date" in df.columns else df.columns[0]
        open_days = set(pd.Timestamp(d).strftime("%Y-%m-%d") for d in df[col])
    except Exception as e:
        sys.stderr.write("交易日历数据列异常：%s——保留旧表。\n" % e)
        return 1

    with open(CALENDAR, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    changed = 0
    for r in rows:
        new = "1" if r["date"] in open_days else "0"
        if r["a_stock"] != new:
            r["a_stock"] = new
            changed += 1
    rows.sort(key=lambda r: r["date"])

    lo, hi = rows[0]["date"], rows[-1]["date"]
    if args.dry_run:
        print("dry-run：a_stock 列将变更 %d 行（范围 %s ~ %s，不写回）" % (changed, lo, hi))
        return 0
    if changed == 0:
        print("交易日历已最新（范围 %s ~ %s，0 行变更）" % (lo, hi))
        return 0
    with open(CALENDAR, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print("交易日历已更新：a_stock 列 %d 行变更（范围 %s ~ %s）" % (changed, lo, hi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
