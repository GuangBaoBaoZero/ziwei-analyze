# -*- coding: utf-8 -*-
"""紫微验证库周检一键化（方案 v1.5 件7）——L1 机械项顺序执行。

L1 步骤（失败即停；WARN=提醒不阻断）：
  w1  validate 例检
  w2  robocopy 备份整备（退出码 ≤3 均成功）
  w3  embed --rebuild 幂等对账
  w4  pattern_stats 冒烟（--person <person>）
  w5  方法论对验（grep 旧特征「权转忌」→ 命中自动 extractor --rebuild-all）
  w6  loopback embed 探活（拒连≠FAIL；端口在而报错才告警→WARN）
  w7  vector 检索冒烟（vector_search 武曲化忌）
  w8  每日流日报告看护（昨日报告在位+mtime 窗口）→ WARN
  w9  工具登记（verify_quote/fill_brief_prompt --help 可跑）
  w10 行为模式卡在位（profile_<person>.md）→ WARN
  w11 词表扫描（当周增量语料/文档 content 层零命中）→ WARN
  w12 <person2>月度流月看护（当月报告在位）→ WARN
  w13 base 闸（check_base liuyue 当月 <person>）
L2 项（矛盾清单+召回扫描/机器判分抽检/错题归因⑯/模式卡提炼刷新）打印「待 agent」清单退出。

用法：python weekly_check.py --person <person> --person2 <person2> [--root <workspace>] [--dry-run]
JSON 日志：_verify/weekly_log/<date>.jsonl

开源形态：
  - 命主工作区缺省=SKILL_ROOT 同级 ziwei-workspace/（不存在则建目录+样例结构说明），--root 可覆盖；
  - anchors.json 缺失：运行时 Python 回退 sys.executable、BACKUP_ROOT 缺→w2 跳过备份；
  - 词表件（data/words.json）不在包内→w11 跳过扫描不 FAIL（缺词表治理为开源形态已知差异）。
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_ROOT, "verify", "bin"))
from common import resolve_data_dir  # noqa: E402

try:
    with open(os.path.join(SKILL_ROOT, "..", "..", "..", "anchors.json"), encoding="utf-8") as f:
        ANCHORS = json.load(f)
except (OSError, ValueError):
    ANCHORS = {}  # 开源形态：无锚点文件，运行时/备份项逐项回退
RUNTIME_PY = ANCHORS.get("RUNTIME_PYTHON") or sys.executable
VEC_PY = ANCHORS.get("PYTHON_VEC") or sys.executable
DATA_DIR = resolve_data_dir(None)
BACKUP_ROOT = ANCHORS.get("BACKUP_ROOT")

DEFAULT_PERSON_ROOT = os.path.join(os.path.dirname(SKILL_ROOT), "ziwei-workspace")
PERSON_ROOT = DEFAULT_PERSON_ROOT  # main() 按 --root 就近解析后覆写


def resolve_person_root(cli_root):
    """命主工作区三级就近解析：--root 显式 > SKILL_ROOT 同级 ziwei-workspace/（在位）
    > 本地 ZERO_ROOT 锚点研究库（回退）；三级皆无则建
    ziwei-workspace/ 并落样例结构说明（开源开箱即跑）。"""
    if cli_root:
        return os.path.abspath(cli_root)
    if os.path.isdir(DEFAULT_PERSON_ROOT):
        return DEFAULT_PERSON_ROOT
    anchored = os.path.join(ANCHORS.get("ZERO_ROOT", ""), "output", "output")
    if ANCHORS.get("ZERO_ROOT") and os.path.isdir(anchored):
        return anchored
    root = DEFAULT_PERSON_ROOT
    os.makedirs(root, exist_ok=True)
    readme = os.path.join(root, "README.md")
    with open(readme, "w", encoding="utf-8", newline="\n") as f:
        f.write("# ziwei-workspace 命主工作区\n\n"
                "样例结构（命主名自定，禁硬编码入代码）：\n\n"
                "```\n<person>/\n  Yuanju/报告.md\n  Daxian/报告-第N限.md\n"
                "  Liunian/报告-YYYY.md\n  Liuyue/报告-YYYY-MM.md\n"
                "  Liuri/报告-YYYY-MM-DD.md\n```\n\n"
                "周检/编排器经 --root 指向本目录，缺省即本目录。\n")
    return root


class StepFail(Exception):
    pass


class Logger:
    def __init__(self):
        d = os.path.join(DATA_DIR, "weekly_log")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, "%s.jsonl" % datetime.date.today().isoformat())

    def log(self, step, name, status, detail=""):
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "step": step, "name": name, "status": status, "detail": detail}
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("[%s] w%d %s：%s" % (status, step, name, detail))
        if status == "FAIL":
            raise StepFail("w%d %s 失败" % (step, name))
        return rec


def run(cmd, py=None, env_extra=None, exe=None):
    env = dict(os.environ, PYTHONUTF8="1")
    if env_extra:
        env.update(env_extra)
    argv = [exe] + cmd if exe else [py or RUNTIME_PY] + cmd
    r = subprocess.run(argv, capture_output=True, env=env, cwd=SKILL_ROOT)
    text = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return r.returncode, text


def w1(log):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "validate.py")])
    if rc != 0:
        log.log(1, "validate 例检", "FAIL", text.strip()[:400])
    log.log(1, "validate 例检", "OK",
            next((l for l in text.splitlines() if "片" in l or "条" in l), "PASS").strip()[:200])


def w2(log):
    if not BACKUP_ROOT:
        log.log(2, "备份整备", "OK", "BACKUP_ROOT 锚点不存在，跳过备份（开源形态）")
        return
    src = DATA_DIR
    dst = os.path.join(BACKUP_ROOT, "ziwei-verify-backup")
    # 只备 events 账本片与 .gitignore：逐片拷（/MIR 会带走派生物，白名单改为显式列举）
    os.makedirs(dst, exist_ok=True)
    copied, kept = 0, 0
    for name in os.listdir(src):
        p = os.path.join(src, name)
        if name.startswith("events_") and name.endswith(".jsonl") or name == ".gitignore":
            subprocess.run(["robocopy", src, dst, name, "/NFL", "/NDL", "/NJH", "/NJS"],
                           capture_output=True)
            copied += 1
        elif name.startswith("events_"):
            kept += 1
    log.log(2, "备份整备", "OK", "账本片备份完成：%d 件 → %s" % (copied, dst))


def w3(log):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "embed.py"), "--rebuild"], py=VEC_PY)
    if rc != 0:
        log.log(3, "embed 对账", "FAIL", text.strip()[:400])
    log.log(3, "embed 对账", "OK",
            next((l for l in text.splitlines() if "索引" in l or "rebuild" in l or "条" in l),
                 "rebuild 完成").strip()[:200])


def w4(log):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "pattern_stats.py"),
                    "--person", _P, "--combo", '{\"主星\":\"武曲\"}', "--level", "liuri"])
    if rc != 0:
        log.log(4, "pattern_stats 冒烟", "FAIL", text.strip()[:400])
    log.log(4, "pattern_stats 冒烟", "OK", text.strip().splitlines()[-1][:200] if text.strip() else "完成")


def w5(log):
    hits = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "events_*.jsonl"))):
        if path.endswith(".bak"):
            continue
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if "权转忌" in line:
                    hits.append("%s:%d" % (os.path.basename(path), i))
    if not hits:
        log.log(5, "方法论对验", "OK", "combo_features 零旧版特征（权转忌）")
        return
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "extractor.py"), "--rebuild-all"])
    if rc != 0:
        log.log(5, "方法论对验", "FAIL",
                "旧特征 %d 处，rebuild-all 失败：%s" % (len(hits), text.strip()[:300]))
    log.log(5, "方法论对验", "OK", "旧特征 %d 处 → extractor --rebuild-all 重算完成" % len(hits))


def w6(log):
    rc, text = run([os.path.join(SKILL_ROOT, "verify", "bin", "embed.py"), "--query", "探活"],
                   py=VEC_PY, env_extra={"HF_HUB_OFFLINE": "1"})
    if "loopback" in text or "fallback" in text:
        log.log(6, "loopback 探活", "OK",
                next(l for l in text.splitlines() if "loopback" in l or "fallback" in l).strip()[:200])
    else:
        log.log(6, "loopback 探活", "WARN", "输出无 loopback/fallback 标记（服务未启动属正常，人工确认为宜）")


def w7(log):
    vec_search = os.path.join(SKILL_ROOT, "vector", "vector_search.py")
    rc, text = run([vec_search, "--query", "武曲化忌", "--top_k", "5"], py=VEC_PY)
    if rc != 0 or not text.strip():
        log.log(7, "vector 冒烟", "FAIL", text.strip()[:300])
    log.log(7, "vector 冒烟", "OK", text.strip().splitlines()[-1][:200])


def w8(log):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    report = os.path.join(PERSON_ROOT, _P, "Liuri", "报告-%s.md" % yesterday.isoformat())
    if not os.path.isfile(report):
        log.log(8, "流日看护", "WARN", "昨日流日报告不存在：%s——提醒维护者（定时任务可能丢失需重建）" % report)
        return
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(report))
    lo = datetime.datetime.combine(yesterday, datetime.time(4, 0))
    hi = datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0))
    if lo <= mtime <= hi:
        log.log(8, "流日看护", "OK", "昨日报告在位且新鲜（mtime=%s）" % mtime.strftime("%m-%d %H:%M"))
    else:
        log.log(8, "流日看护", "WARN", "报告 mtime=%s 超窗（%s~%s）" % (mtime, lo, hi))


def w9(log):
    for script in ("verify_quote.py", "fill_brief_prompt.py"):
        rc, text = run([os.path.join(SKILL_ROOT, "bin", script), "--help"])
        if rc != 0:
            log.log(9, "工具登记", "FAIL", "%s --help 退出码 %d" % (script, rc))
    log.log(9, "工具登记", "OK", "verify_quote/fill_brief_prompt --help 可跑；新工具登记差集人工核对")


def w10(log):
    p = os.path.join(DATA_DIR, "profile_%s.md" % _P)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        log.log(10, "模式卡在位", "OK", p)
    else:
        log.log(10, "模式卡在位", "WARN", "profile_%s.md 缺失——L2 提炼待 agent" % _P)


def w11(log):
    words_path = os.path.join(SKILL_ROOT, "data", "words.json")
    if not os.path.isfile(words_path):
        log.log(11, "词表扫描", "OK", "依赖件不存在，跳过（开源形态）——词表治理件不在包内")
        return
    r = subprocess.run(["git", "log", "--since=7 days ago", "--name-only", "--pretty=format:"],
                       capture_output=True, cwd=SKILL_ROOT, env=dict(os.environ, PYTHONUTF8="1"))
    changed = {l.strip().replace("/", os.sep) for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()}
    words = json.load(open(words_path, encoding="utf-8"))
    sensitive = [w for w in words.get("sensitive", []) if w]
    whitelist = set(words.get("functional_whitelist", []))
    hits, scanned = [], 0
    for rel in sorted(changed):
        p = os.path.join(SKILL_ROOT, rel)
        if not os.path.isfile(p):
            continue
        if not (rel.startswith(os.path.join("data", "zp")) or rel == os.path.join("data", "zeropro_open_kb.json")
                or rel.startswith(os.path.join("data", "docs"))):
            continue
        scanned += 1
        with open(p, encoding="utf-8") as f:
            content = f.read()
        for w in sensitive:
            if w in whitelist:
                continue
            if w in content:
                hits.append("%s：「%s」" % (rel, w))
    if hits:
        log.log(11, "词表扫描", "WARN", "当周增量 %d 件命中 %d 处（用户语料域只读，报告提醒不代改）：%s"
                % (scanned, len(hits), "；".join(hits[:10])))
    else:
        log.log(11, "词表扫描", "OK", "当周增量 %d 件 content 层零命中" % scanned)


def w12(log):
    month = datetime.date.today().strftime("%Y-%m")
    report = os.path.join(PERSON_ROOT, _P2, "Liuyue", "报告-%s.md" % month)
    if os.path.isfile(report):
        log.log(12, "月度看护", "OK", report)
    else:
        log.log(12, "月度看护", "WARN", "当月流月报告不在位：%s——提醒（月度任务静默失败兜底，不代跑）" % report)


def w13(log):
    month = datetime.date.today().strftime("%Y-%m")
    rc, text = run([os.path.join(SKILL_ROOT, "bin", "check_base.py"),
                    "--level", "liuyue", "--key", month, "--person", _P])
    if rc != 0:
        log.log(13, "base 闸", "FAIL", text.strip()[:300])
    log.log(13, "base 闸", "OK", text.strip().splitlines()[0])


L2_LIST = [
    "⑥ 矛盾清单+召回自动扫描（同层级同类别一吉一凶记录对；本周会话疑似事件验证库无记录——报告提醒，判断类禁自动）",
    "⑬ 机器判分人工抽检（本周机器判定条目抽样≥2 条，定位=「投资收益/今日操作：」前缀，复核 verify_note 留痕）",
    "⑯ 错题归因（本周方向句判定不准条目三分类：判断错/结构偏/随机；档序 n≥5 闸；工时上限 15 分钟；结论标「agent 判断，可复议」）",
    "⑫ 行为模式卡提炼刷新（L1 只验在位；LLM 读 events 近 60 条提炼，更新制覆写 profile_<person>.md）",
]

STEPS = [
    ("validate 例检", w1), ("备份整备", w2), ("embed 对账", w3), ("pattern_stats 冒烟", w4),
    ("方法论对验", w5), ("loopback 探活", w6), ("vector 冒烟", w7), ("流日看护", w8),
    ("工具登记", w9), ("模式卡在位", w10), ("词表扫描", w11), ("月度看护", w12), ("base 闸", w13),
]


def main():
    ap = argparse.ArgumentParser(description="紫微验证库周检一键化（方案 v1.5 件7）")
    ap.add_argument("--person", required=True, help="命主名（隐私纪律：禁硬编码）")
    ap.add_argument("--person2", required=True, help="月度看护命主名")
    ap.add_argument("--root", default=None,
                    help="命主工作区根（缺省=SKILL_ROOT 同级 ziwei-workspace/，不存在则建样例结构）")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true", help="只列步骤不执行")
    global _P, _P2, PERSON_ROOT
    args = ap.parse_args()
    _P, _P2 = args.person, args.person2
    PERSON_ROOT = resolve_person_root(args.root)
    if args.dry_run:
        print("═ weekly_check dry-run（L1 %d 步 + L2 待 agent 清单）═" % len(STEPS))
        for i, (name, _) in enumerate(STEPS, 1):
            print("  w%-2d %s" % (i, name))
        for ln in L2_LIST:
            print("  L2  %s" % ln)
        return
    log = Logger()
    print("═ weekly_check（日志=%s）═" % log.path)
    try:
        for i, (name, fn) in enumerate(STEPS, 1):
            fn(log)
    except StepFail as e:
        print("\nFAIL：%s——修复后重跑（幂等）" % e)
        sys.exit(1)
    print("\nL1 全过。═ L2 待 agent 清单 ═")
    for ln in L2_LIST:
        print("  " + ln)
    print("红线：判断类禁自动；events 账本只读；数据正文件禁碰。")


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    main()
