# -*- coding: utf-8 -*-
"""查询印证账本。用法：
query.py --person 名 [--level 层] [--category 类] [--scope self|cross] [--data-dir 目录] [--limit 50]
self=指定命主全量（全字段）；cross=全部命主（脱敏投影：person→"另一命主"、text→category、日期截到月）。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import list_shards, out, read_lines, resolve_data_dir

CROSS_FIELDS = ["person", "event_date", "date_precision", "level", "category",
                "verify_result", "judged_by", "created_at"]


def load(data_dir, owner=None):
    recs = []
    for _, _, name in list_shards(data_dir, owner):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    return recs


def month_granularity(date_str):
    # 精度截到月：YYYY-MM-DD → YYYY-MM；YYYY / YYYY-MM 原样（不虚构精度）
    parts = date_str.split("-")
    return "-".join(parts[:2])


def main():
    ap = argparse.ArgumentParser(description="查询印证账本")
    ap.add_argument("--person", required=True)
    ap.add_argument("--level", default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--scope", choices=["self", "cross"], default="self")
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    if args.scope == "self":
        recs = load(data_dir, owner=args.person)
    else:
        recs = load(data_dir)

    def keep(r):
        if args.level is not None and (r.get("level") or "") != args.level:
            return False
        if args.category is not None and r.get("category") != args.category:
            return False
        return True

    recs = [r for r in recs if keep(r)][:max(0, args.limit)]

    if args.scope == "self":
        for r in recs:
            out(json.dumps(r, ensure_ascii=False))
    else:
        for r in recs:
            proj = {k: r.get(k) for k in CROSS_FIELDS}
            proj["person"] = "另一命主"
            proj["text"] = proj.get("category")  # 脱敏：不输出原文
            proj["event_date"] = month_granularity(proj.get("event_date") or "")
            proj["date_precision"] = "month" if proj["event_date"] else ""
            out(json.dumps(proj, ensure_ascii=False))
    out("共 %d 条" % len(recs))


if __name__ == "__main__":
    main()
