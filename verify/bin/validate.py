# -*- coding: utf-8 -*-
"""校验印证账本全部 events_*.jsonl：行 JSON 合法、必填字段齐、event_id 全库唯一、
非末片恒满（≥分片阈值）、owner 与文件名一致。全过 exit 0，任一 FAIL exit 1。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SHARD_RE, list_shards, out, read_lines, resolve_data_dir, shard_size

REQUIRED = ["event_id", "person", "event_date", "date_precision",
            "category", "text", "verify_result", "created_at"]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", dest="data_dir", default=None)
    args = ap.parse_args()
    data_dir = resolve_data_dir(args.data_dir)

    shards = list_shards(data_dir)
    if not shards:
        out("（空库）无分片可校验")
        sys.exit(0)

    size = shard_size()
    all_ids = {}
    owners_last = {}
    for owner, num, name in shards:
        owners_last[owner] = max(owners_last.get(owner, 0), num)

    fail = False
    for owner, num, name in shards:
        path = os.path.join(data_dir, name)
        problems = []
        count = 0
        ids_here = []
        for line in read_lines(path):
            count += 1
            try:
                rec = json.loads(line)
            except ValueError as e:
                problems.append("第%d行 JSON 非法: %s" % (count, e))
                continue
            missing = [k for k in REQUIRED if k not in rec or rec[k] in (None, "")]
            if missing:
                problems.append("第%d行缺必填字段: %s" % (count, ",".join(missing)))
            eid = rec.get("event_id")
            if eid:
                if eid in all_ids:
                    problems.append("event_id 重复: %s（亦见于 %s）" % (eid, all_ids[eid]))
                else:
                    all_ids[eid] = name
                ids_here.append(eid)
            if rec.get("person") != owner:
                problems.append("第%d行 person(%r) 与文件名 owner(%s) 不一致" % (count, rec.get("person"), owner))
            if "theory" in rec and not isinstance(rec.get("theory"), str):
                problems.append("第%d行 theory 须为字符串（可选字段）" % count)
        if num < owners_last[owner] and count < size:
            problems.append("非末片未满：条数 %d < 分片阈值 %d" % (count, size))
        if problems:
            fail = True
            out("FAIL %s：%s" % (name, "；".join(problems)))
        else:
            out("PASS %s（%d 条）" % (name, count))

    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
