#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ziwei-analyze 五行自检：安装后运行 python bin/selfcheck.py。

① 知识库加载（动态打印切片数） ② paipan.js 排虚构盘 ③ taxonomy 检索通路
④ 输出目录可写 ⑤ 向量引擎三态探测（faiss 未装/模型未缓存→OPTIONAL，齐备→browse 实测）。
前四项 PASS + 第⑤项 PASS/OPTIONAL = 环境就绪；任一 FAIL = exit 1。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ok = True

    # ① 知识库加载
    kb_path = os.path.join(ROOT, "data", "zeropro_open_kb.json")
    try:
        with open(kb_path, encoding="utf-8") as f:
            slices = json.load(f)
        assert len(slices) > 0
        print("[1/5] 知识库加载 PASS（%d 片）" % len(slices))
    except Exception as e:
        ok = False
        print("[1/5] 知识库加载 FAIL：%s" % e)

    # ② 排盘引擎（Node，虚构生辰）
    node = os.environ.get("NODE_BIN", "node")
    try:
        r = subprocess.run(
            [node, os.path.join(ROOT, "engine", "paipan.js"),
             "--birth", "1995-06-15 12:30", "--gender", "male"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            print("[2/5] 排盘引擎 PASS（paipan.js exit 0）")
        else:
            ok = False
            print("[2/5] 排盘引擎 FAIL：exit=%s stderr=%s" % (r.returncode, r.stderr[:200]))
    except Exception as e:
        ok = False
        print("[2/5] 排盘引擎 FAIL：%s（检查 Node.js >= 14 已安装）" % e)

    # ③ taxonomy 检索通路
    try:
        sys.path.insert(0, os.path.join(ROOT, "core"))
        import retrieve
        import taxonomy
        data = retrieve.load_kb_data()
        assert len(taxonomy.MAIN_STARS) > 0 and len(data) > 0
        print("[3/5] taxonomy 检索通路 PASS（主星 %d / 知识库 %d 片）"
              % (len(taxonomy.MAIN_STARS), len(data)))
    except Exception as e:
        ok = False
        print("[3/5] taxonomy 检索通路 FAIL：%s" % e)

    # ④ 输出目录可写
    try:
        outdir = os.path.join(ROOT, "output")
        os.makedirs(outdir, exist_ok=True)
        probe = os.path.join(outdir, ".selfcheck_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        print("[4/5] 输出目录可写 PASS（%s）" % outdir)
    except Exception as e:
        ok = False
        print("[4/5] 输出目录可写 FAIL：%s" % e)

    # ⑤ 向量引擎三态探测
    try:
        import faiss  # noqa: F401
    except ImportError:
        print("[5/5] 向量引擎 OPTIONAL（未安装 faiss——语义检索档未启用，安装见 requirements-vec.txt）")
        sys.exit(0 if ok else 1)
    bge_cached = False
    hf_bases = [os.environ.get("HF_HOME") or "",
                os.path.join(os.path.expanduser("~"), ".cache", "huggingface")]
    for base in hf_bases:
        if base and os.path.isdir(os.path.join(
                base, "hub", "models--BAAI--bge-small-zh-v1.5")):
            bge_cached = True
            break
    if not bge_cached:
        print("[5/5] 向量引擎 OPTIONAL（bge 模型未缓存——首次运行需联网下载约 100MB，"
              "国内建议设 HF_ENDPOINT=https://hf-mirror.com，见 vector/README.md）")
        sys.exit(0 if ok else 1)
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "vector", "vector_search.py"), "--browse"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            print("[5/5] 向量引擎 PASS（vector_search.py --browse exit 0）")
        else:
            ok = False
            print("[5/5] 向量引擎 FAIL：exit=%s stderr=%s"
                  % (r.returncode, (r.stderr or r.stdout)[:200]))
    except Exception as e:
        ok = False
        print("[5/5] 向量引擎 FAIL：%s" % e)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
