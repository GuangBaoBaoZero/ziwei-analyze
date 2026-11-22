#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""向量检索环境自动配置器（依赖检测/安装 + 模型/索引在位检测 + 真查询自检）。

用法：
  python setup_vector.py               # 检测→缺啥装啥→自检→就绪报告
  python setup_vector.py --check-only  # 只检不装

检测项：
  ① 依赖包：faiss-cpu / numpy / sentence-transformers / jieba / rank-bm25
     （逐个 pip install，失败明确报错并给手动指引；--check-only 跳过安装）
  ② 本地模型：vector/models/bge-small-zh（skill 根，随包提供）
  ③ kb_index 三件：vectors.index / metadata.db / bm25.cache
     （vector/kb_index）
     classics faiss 索引若存在（classics_faiss.index / classics_bm25.pkl / classics_meta.db）一并检
  ④ 真查询自检：vector_search.py --query 测试 一条实跑
  ⑤ 就绪报告：装了什么 / 缺什么 / 下一步
禁读 .env。PYTHONUTF8=1 兼容。
"""
import argparse
import importlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))

# import 名 → pip 包名
DEPS = [
    ("faiss", "faiss-cpu"),
    ("numpy", "numpy"),
    ("sentence_transformers", "sentence-transformers"),
    ("jieba", "jieba"),
    ("rank_bm25", "rank-bm25"),
]

MODEL_DIRS = [
    os.path.join(SKILL_ROOT, "vector", "models", "bge-small-zh"),
]

KB_INDEX_DIRS = [
    os.path.join(SKILL_ROOT, "vector", "kb_index"),
]
KB_INDEX_FILES = ["vectors.index", "metadata.db", "bm25.cache"]

SEARCH_SCRIPTS = [
    os.path.join(SKILL_ROOT, "vector", "vector_search.py"),
]

CLASSICS_FAISS_FILES = [
    os.path.join(SKILL_ROOT, "data", "classics_faiss.index"),
    os.path.join(SKILL_ROOT, "data", "classics_meta.db"),
]


def find_first(candidates, isdir=False):
    for c in candidates:
        if os.path.isdir(c) if isdir else os.path.isfile(c):
            return c
    return None


def check_deps():
    missing = []
    for mod, pkg in DEPS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    return missing


def install_deps(packages):
    installed, failed = [], []
    for pkg in packages:
        print(f"[install] pip install {pkg} ...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                           capture_output=True, text=True)
        if r.returncode == 0:
            ok = False
            for m, p in DEPS:
                if p == pkg:
                    try:
                        importlib.import_module(m)
                        ok = True
                    except ImportError:
                        ok = False
            if ok:
                installed.append(pkg)
                print(f"[install] {pkg} OK")
            else:
                failed.append(pkg)
                print(f"[FAIL] {pkg} pip 返回 0 但 import 失败", file=sys.stderr)
        else:
            failed.append(pkg)
            print(f"[FAIL] pip install {pkg} 失败（exit {r.returncode}）：",
                  file=sys.stderr)
            print(r.stderr[-800:] if r.stderr else "(无 stderr)", file=sys.stderr)
    return installed, failed


def run_query_selftest():
    script = find_first(SEARCH_SCRIPTS)
    if script is None:
        return None, "vector_search.py 未找到（vector/ 子模块与姊妹 core 均缺席）"
    # 与本进程检测环境同源：继承 sys.path（第三方装在非默认 site-packages 时子进程 import 才不假缺）
    env = dict(os.environ, PYTHONUTF8="1",
               PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    r = subprocess.run([sys.executable, script, "--query", "测试", "--top_k", "3"],
                       capture_output=True, text=True, env=env, timeout=300)
    if r.returncode == 0 and r.stdout.strip():
        return True, script
    msg = (r.stderr or r.stdout or "").strip().splitlines()
    return False, " | ".join(msg[-3:]) if msg else f"exit {r.returncode}"


def main():
    ap = argparse.ArgumentParser(description="向量检索环境自动配置器")
    ap.add_argument("--check-only", action="store_true", help="只检测不安装")
    args = ap.parse_args()

    print("=" * 56)
    print("向量检索环境配置报告")
    print("=" * 56)
    print(f"解释器：{sys.executable}")

    # ① 依赖
    missing = check_deps()
    if missing:
        print(f"\n[1/5] 依赖：缺 {len(missing)}/{len(DEPS)} → {', '.join(missing)}")
        if args.check_only:
            print("      --check-only：跳过安装")
            installed, failed = [], missing
        else:
            print("      开始安装依赖（预计 1-3 分钟，期间无输出属正常）")
            installed, failed = install_deps(missing)
            if installed:
                print(f"      已安装：{', '.join(installed)}")
            if failed:
                print(f"      仍缺：{', '.join(failed)}")
                print("      手动指引：python -m pip install " + " ".join(failed))
    else:
        print(f"\n[1/5] 依赖：{len(DEPS)}/{len(DEPS)} 全部在位")
        installed, failed = [], []

    deps_ready = not check_deps() and not failed

    # ② 模型
    model = find_first(MODEL_DIRS, isdir=True)
    if model:
        n = len([f for f in os.listdir(model) if f.endswith(".safetensors")])
        print(f"[2/5] 本地模型：在位 → {model}（safetensors {n} 个）")
    else:
        print("[2/5] 本地模型：缺失（vector/models/bge-small-zh 与姊妹目录位均无）")
        print("      模型已随包（vector/models）；若缺失方联网下载 BAAI/bge-small-zh-v1.5")

    # ③ kb_index 三件 + classics faiss（若存在）
    kb_dir = find_first(KB_INDEX_DIRS, isdir=True)
    if kb_dir:
        have = [f for f in KB_INDEX_FILES if os.path.isfile(os.path.join(kb_dir, f))]
        lack = [f for f in KB_INDEX_FILES if f not in have]
        if lack:
            print(f"[3/5] kb_index：{kb_dir} 缺 {lack}")
        else:
            print(f"[3/5] kb_index：三件齐全 → {kb_dir}")
    else:
        print("[3/5] kb_index：目录缺失（vector/kb_index 与姊妹目录 data/kb_index 均无）")

    if any(os.path.isfile(f) for f in CLASSICS_FAISS_FILES):
        have = [os.path.basename(f) for f in CLASSICS_FAISS_FILES if os.path.isfile(f)]
        lack = [os.path.basename(f) for f in CLASSICS_FAISS_FILES if not os.path.isfile(f)]
        state = "齐全" if not lack else f"缺 {lack}"
        print(f"      classics faiss 索引：{state}（{have if have else '无'}）")
        if lack:
            print("      构建：python bin/classics_build_index.py --engine faiss")
    else:
        print("      classics faiss 索引：不存在（如需语义检索 classics：")
        print("      python bin/classics_build_index.py --engine faiss）")

    # ④ 真查询自检
    if not deps_ready:
        print("[4/5] 自检：跳过（依赖不全）")
        qt, qm = None, "依赖不全"
    elif not kb_dir:
        print("[4/5] 自检：跳过（kb_index 缺失）")
        qt, qm = None, "kb_index 缺失"
    else:
        print("[4/5] 真查询自检：vector_search.py --query 测试 ...")
        qt, qm = run_query_selftest()
        if qt:
            print("      [OK] 查询返回结果")
        else:
            print(f"      [FAIL] {qm}")

    # ⑤ 就绪报告
    print("-" * 56)
    if installed:
        print(f"本轮安装：{', '.join(installed)}")
    else:
        print("本轮安装：无")
    problems = []
    if check_deps():
        problems.append("依赖仍缺：" + ", ".join(check_deps()))
    if not model:
        problems.append("本地模型缺失（vector/models 应随包提供，缺失可联网补下载）")
    if not kb_dir:
        problems.append("kb_index 缺失")
    if qt is False:
        problems.append("自检失败：" + str(qm))
    if problems:
        print("仍缺 / 下一步：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("全部就绪：依赖 / 模型 / kb_index / 真查询自检 全过。")

    # ⑥ 交易日历顺带更新（失败仅提示不阻断）
    print("-" * 56)
    print("[6/6] 交易日历更新：update_trade_calendar.py ...")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "update_trade_calendar.py")])
    if rc == 0:
        print("      [OK] 交易日历为最新")
    else:
        print("      [提示] 交易日历未更新（退出码 %d，可稍后手动跑 bin/update_trade_calendar.py），不阻断。" % rc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
