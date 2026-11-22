# -*- coding: utf-8 -*-
"""紫微产线底座存在性闸：流日跑批前检查上层底座报告是否在位。

用法：
    python check_base.py --level liuyue --key 2026-11 [--person <命主名>] [--zero-root PATH]
                          [--root 产物根目录]

  --root   产物根目录（其下 <person>/<Liuyue|Liunian>/报告-*.md）；缺省经
           --zero-root/anchors/env ZERO_ROOT 解析 <ZERO_ROOT>/output/output
退出码：0=底座在位；1=缺失；2=参数非法。
"""
import argparse
import io
import json
import os
import pathlib
import re
import sys

LEVEL_DIRS = {"liuyue": "Liuyue", "liunian": "Liunian"}
KEY_PATTERNS = {"liuyue": r"^\d{4}-\d{2}$", "liunian": r"^\d{4}$"}
DEFAULT_PERSON = os.environ.get("ZIWEI_PERSON", "")


def resolve_zero_root(override):
    if override:
        return override
    anchors_path = pathlib.Path(__file__).resolve().parents[4] / "anchors.json"
    try:
        with io.open(anchors_path, "r", encoding="utf-8") as f:
            anchors = json.load(f)
        value = anchors.get("ZERO_ROOT")
        if value:
            return value
    except (OSError, ValueError):
        pass
    env = os.environ.get("ZERO_ROOT")
    if env:
        return env
    sys.stderr.write("ARG-ERR 无法确定 ZERO_ROOT：anchors.json 解析失败或缺键，且环境变量 ZERO_ROOT 未设置\n")
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="紫微产线底座存在性闸")
    parser.add_argument("--level", required=True, choices=None,
                        help="底座层级：liuyue 或 liunian")
    parser.add_argument("--key", required=True,
                        help="liuyue 配 YYYY-MM；liunian 配 YYYY")
    parser.add_argument("--person", default=DEFAULT_PERSON)
    parser.add_argument("--zero-root", default=None,
                        help="覆盖 ZERO_ROOT（缺省读 anchors.json）")
    parser.add_argument("--root", default=None,
                        help="产物根目录（缺省 <ZERO_ROOT>/output/output）")
    args = parser.parse_args()

    if args.level not in LEVEL_DIRS:
        sys.stderr.write("ARG-ERR --level 须为 liuyue 或 liunian，收到：%s\n" % args.level)
        sys.exit(2)
    if not re.match(KEY_PATTERNS[args.level], args.key):
        want = "YYYY-MM" if args.level == "liuyue" else "YYYY"
        sys.stderr.write("ARG-ERR --key 格式与 --level %s 不匹配（须为 %s），收到：%s\n"
                         % (args.level, want, args.key))
        sys.exit(2)

    if args.root:
        base_root = os.path.abspath(args.root)
    else:
        zero_root = resolve_zero_root(args.zero_root)
        base_root = os.path.join(zero_root, "output", "output")
    report = os.path.join(
        base_root, args.person,
        LEVEL_DIRS[args.level], "报告-%s.md" % args.key,
    )
    if os.path.isfile(report):
        print("BASE-OK %s" % report)
        sys.exit(0)
    print("BASE-MISSING %s——先生成底座再继续（编排见 docs/pipeline_layers.md）" % report)
    sys.exit(1)


if __name__ == "__main__":
    main()
