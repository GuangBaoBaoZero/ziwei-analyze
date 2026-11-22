# -*- coding: utf-8 -*-
"""通用收益数据导入（开源用户入口：任意 UTF-8 CSV → read_returns 同构 entry）。

把用户自备的收益 CSV 转成与 read_returns.py 相同形态的条目字典，供
auto_judge_returns / rebuild_total_caliber 等收益环工具消费——开源部署无需
本地账本 xlsx，只需自备 CSV。

CSV 格式（UTF-8，首行表头，列序任意，多余列忽略）：
    date,total[,stock,futures]
  - date：YYYY-MM-DD
  - total：当日总资金余额；列缺失时 = stock+futures 自算（此时须有 stock、futures 两列）
  - stock/futures：当日分端资金余额（可选；缺列则分端收益率输出 null）
数值一律按「资金余额」口径，收益率 = 相对 CSV 中上一交易日的日变动%
（与 read_returns 的合并余额口径同构：total=股票+期货合并日变动%）。

用法：
    python returns_import.py --csv returns.csv [--date YYYY-MM-DD]
    python returns_import.py --make-sample sample_returns.csv
  --date        取该日条目；缺省取最新一日（首行无前日参照 → total=no_data）
  --make-sample 生成虚构样例 CSV 到指定路径后退出（数据纯属虚构，仅作格式示范）

输出：单条 entry JSON（与 read_returns 同构）：
  date/total/total_return/stock_return/futures_return/stock_pnl/futures_pnl；
  无该日数据时输出 {"status":"no_data",...}。
零第三方依赖；零硬编码绝对路径；禁读 .env。
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta

FIELDS = ("date", "total", "stock", "futures")


def make_sample(path):
    """虚构样例 CSV：5 个连续交易日，余额数据纯属虚构。"""
    base = datetime(2026, 1, 5)
    rows = [
        ("2026-01-05", "", "100000", "50000"),
        ("2026-01-06", "", "100500", "49800"),
        ("2026-01-07", "", "100200", "50300"),
        ("2026-01-08", "", "101000", "50500"),
        ("2026-01-09", "", "100800", "50100"),
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow(r)
    print("样例 CSV 已生成：%s（数据虚构，仅作格式示范）" % path)


def parse_num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        raise SystemExit("错误：数值列不可解析：%r（须为数字资金余额）" % v)


def load_rows(path):
    """CSV → [(date, total, stock, futures)] 按日期升序。"""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = [h.strip() for h in (reader.fieldnames or [])]
            has_total = "total" in header
            if not has_total and ("stock" not in header or "futures" not in header):
                raise SystemExit("错误：表头须为 date,total[,stock,futures]——"
                                 "缺 total 列时必须有 stock、futures 列；实际表头：%s"
                                 % ",".join(header))
            if "date" not in header:
                raise SystemExit("错误：表头缺 date 列；实际表头：%s" % ",".join(header))
            out = []
            for row in reader:
                d = (row.get("date") or "").strip()[:10]
                if not d:
                    continue
                stock = parse_num(row.get("stock"))
                futures = parse_num(row.get("futures"))
                if has_total and (row.get("total") or "").strip() != "":
                    total = parse_num(row.get("total"))
                elif stock is not None and futures is not None:
                    total = stock + futures
                else:
                    total = None
                out.append((d, total, stock, futures))
    except OSError as e:
        raise SystemExit("错误：无法读取 CSV %s：%s" % (path, e))
    if not out:
        raise SystemExit("错误：CSV 无数据行：%s" % path)
    out.sort(key=lambda r: r[0])
    return out


def build_entry(rows, date_arg):
    """rows（升序）→ 目标日 entry（与 read_returns 同构）。"""
    dates = [r[0] for r in rows]
    idx = len(rows) - 1 if date_arg is None else (
        dates.index(date_arg) if date_arg in dates else -1)
    if idx < 0:
        print(json.dumps({"status": "no_data",
                          "message": "%s 无收益数据" % (date_arg or "最新交易日")},
                         ensure_ascii=False))
        return None
    d, total, stock, futures = rows[idx]
    entry = {"date": d, "total": "no_data", "total_return": None,
             "stock_return": None, "futures_return": None,
             "stock_pnl": None, "futures_pnl": None,
             "stock_balance": stock, "futures_balance": futures}
    if idx == 0 or total is None:
        return entry
    _, prev_total, prev_stock, prev_futures = rows[idx - 1]
    if prev_total not in (None, 0):
        ret = total / prev_total - 1
        entry["total"] = ret
        entry["total_return"] = ret
    if stock is not None and prev_stock not in (None, 0):
        entry["stock_return"] = stock / prev_stock - 1
        entry["stock_pnl"] = stock - prev_stock
    if futures is not None and prev_futures not in (None, 0):
        entry["futures_return"] = futures / prev_futures - 1
        entry["futures_pnl"] = futures - prev_futures
    return entry


def main():
    ap = argparse.ArgumentParser(description="通用收益 CSV 导入（read_returns 同构输出）")
    ap.add_argument("--csv", dest="csv_path", default="",
                    help="收益 CSV 路径（表头 date,total[,stock,futures]）")
    ap.add_argument("--date", dest="date", default="",
                    help="取该日条目；缺省取最新一日")
    ap.add_argument("--make-sample", dest="make_sample", default="",
                    help="生成虚构样例 CSV 到指定路径后退出")
    args = ap.parse_args()

    if args.make_sample:
        make_sample(args.make_sample)
        return
    if not args.csv_path:
        ap.error("须提供 --csv（或 --make-sample 生成样例）")

    entry = build_entry(load_rows(args.csv_path), args.date or None)
    if entry is not None:
        print(json.dumps(entry, ensure_ascii=False, default=str))


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
