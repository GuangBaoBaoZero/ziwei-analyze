# -*- coding: utf-8 -*-
"""补发循环脚本生成器（方案 v1.5 件5）。

输入 = check_outputs 的 FAIL 输出（stdin / --fail-file），或 --dir 批次目录自跑
check_outputs 解析。按 FAIL 宫生成补发 workflow 脚本（复用批次目录内
dispatch_liupan.workflow.js 的 CONFIG/runPalace/runPool 前缀，主段改为仅跑
FAIL 宫 + 注入双保 prompt：结论字数 800-1400 与级联引用两条硬要求 + 禁越层
判语），输出到批次目录 refill_<n>.workflow.js（供后台执行）。

轮次封顶：按目录内既有 refill_*.workflow.js 计数，下一轮编号 > --rounds
（默认 3）时不再生成，打印转人工提示并以 exit 2 结束。

用法：
  python refill.py --dir <批次目录> [--rounds 3]                # 自跑点检
  python refill.py --dir <批次目录> --fail-file <check输出.txt>  # 喂点检输出
  check_outputs ... | python refill.py --dir <批次目录>          # stdin 喂入
"""

import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL_RE = re.compile(r'^FAIL\s+(\S+)')
DISPATCH_MAIN_MARK = "phase('dispatch-liupan"


def parse_fail_palaces(text):
    """从 check_outputs 输出解析 FAIL 宫名列表（去重保序）。"""
    palaces = []
    for line in text.splitlines():
        m = FAIL_RE.match(line.strip())
        if m:
            name = m.group(1)
            if name not in palaces:
                palaces.append(name)
    return palaces


def next_round(batch_dir, rounds):
    """既有 refill_*.workflow.js 计数 → 下一轮编号；超 --rounds 返回 None。"""
    used = [int(m.group(1)) for p in glob.glob(os.path.join(batch_dir, 'refill_*.workflow.js'))
            for m in [re.match(r'^refill_(\d+)\.workflow\.js$', os.path.basename(p))] if m]
    n = (max(used) + 1) if used else 1
    return n if n <= rounds else None


def build_script(template, palaces, reasons, n):
    """从 dispatch 模板截取 CONFIG+helpers 前缀，接补发主段。"""
    idx = template.find(DISPATCH_MAIN_MARK)
    if idx < 0:
        raise SystemExit('错误：dispatch_liupan.workflow.js 中未找到主段标记 %s' % DISPATCH_MAIN_MARK)
    prefix = template[:idx]
    pal_js = json_js_list(palaces)
    reason_lines = '\n'.join('//   %s：%s' % (p, reasons.get(p, '')) for p in palaces)
    tail = (
        '// ══ 补发主段（refill.py 第 %d 轮生成）══\n'
        '// 上轮 FAIL 及原因：\n%s\n'
        'const FAIL_PALACES = %s;\n'
        '\n'
        '// 双保 prompt 注入：字数 800-1400 + 级联引用两硬要求 + 禁越层判语\n'
        'const _origPalacePrompt = palacePrompt;\n'
        'palacePrompt = function (idx, name) {\n'
        '  const r = _origPalacePrompt(idx, name);\n'
        '  r.usr += \'\\n\\n【补发硬要求】（上轮点检 FAIL，本轮逐条必须全部满足）\\n\'\n'
        '    + \'1. 字数硬要求：「## \' + name + \' 结论」节正文中文字符数必须在 800-1400 之间（去空白逐字计）——不足 800 与超 1400 同为失败，请写足 1000 字上下。\\n\'\n'
        '    + \'2. 级联引用硬要求：输入若含【上级分析结论参考】，output 正文必须出现「上级」字样并实际引用其已判定结论。\\n\'\n'
        '    + \'3. 禁越层判语：时间表述只用本层词汇（今日/当日），禁用「大限十年」「流年全年」「此十年」等更远层判语；行运判语只用[主][辅]合法组合。\';\n'
        '  return r;\n'
        '};\n'
        '\n'
        "phase('refill-%d');\n"
        'log(`补发第 %d 轮：${FAIL_PALACES.join(\'、\')} 共 ${FAIL_PALACES.length} 宫（双池滚动，任一失败自动换池重发）`);\n'
        'const tasks = FAIL_PALACES.map(n => ({ idx: PALACES.indexOf(n), name: n })).filter(t => t.idx >= 0);\n'
        'if (tasks.length < FAIL_PALACES.length) {\n'
        '  const bad = FAIL_PALACES.filter(n => PALACES.indexOf(n) < 0);\n'
        "  log(`警告：宫名不在十二宫序：${bad.join('、')}——已跳过`);\n"
        '}\n'
        'const results = await runPool(CONFIG.providerA, tasks);\n'
        'const okN = results.filter(x => x.ok).length;\n'
        'log(`补发完成 ${okN}/${tasks.length}——重跑 check_outputs 复核，仍有 FAIL 且未达轮次上限则再生成下一轮`);\n'
        'return { round: %d, okCount: okN, palaces: FAIL_PALACES, results };\n'
    ) % (n, reason_lines, pal_js, n, n, n)
    return prefix + tail


def json_js_list(items):
    return '[' + ', '.join("'%s'" % i for i in items) + ']'


def main():
    ap = argparse.ArgumentParser(description='按 check_outputs FAIL 宫生成补发 workflow 脚本')
    ap.add_argument('--dir', required=True, help='批次目录（含 dispatch_liupan.workflow.js 与 input/output）')
    ap.add_argument('--fail-file', default=None, help='check_outputs 输出文件（缺省：有 stdin 则读 stdin，否则自跑）')
    ap.add_argument('--rounds', type=int, default=3, help='补发轮次封顶（默认 3，超出转人工）')
    args = ap.parse_args()

    batch_dir = os.path.abspath(args.dir)
    if not os.path.isdir(batch_dir):
        raise SystemExit('错误：批次目录不存在：%s' % batch_dir)
    dispatch = os.path.join(batch_dir, 'dispatch_liupan.workflow.js')
    if not os.path.isfile(dispatch):
        raise SystemExit('错误：批次目录缺 dispatch_liupan.workflow.js：%s' % dispatch)

    # 取 check_outputs 输出：--fail-file > stdin > 自跑
    if args.fail_file:
        with open(args.fail_file, encoding='utf-8') as f:
            check_text = f.read()
    elif not sys.stdin.isatty():
        check_text = sys.stdin.read()
    else:
        print('自跑 check_outputs：%s' % batch_dir, file=sys.stderr)
        r = subprocess.run([sys.executable, os.path.join(HERE, 'check_outputs.py'), '--dir', batch_dir],
                           capture_output=True, text=True, encoding='utf-8')
        check_text = r.stdout
        if r.returncode == 0:
            print(check_text.strip())
            print('12 宫全 PASS，无需补发')
            return
        print(check_text.strip(), file=sys.stderr)

    palaces = parse_fail_palaces(check_text)
    if not palaces:
        print('FAIL 输出中未解析到宫名，无补发对象')
        return
    reasons = {}
    for line in check_text.splitlines():
        m = FAIL_RE.match(line.strip())
        if m:
            reasons[m.group(1)] = line.strip()[len(m.group(0)):].strip()

    n = next_round(batch_dir, args.rounds)
    if n is None:
        done = len(glob.glob(os.path.join(batch_dir, 'refill_*.workflow.js')))
        print('转人工提示：补发已达 %d 轮封顶（--rounds=%d），FAIL 宫=%s——'
              '请人工串行补跑或人工撰写这些宫的分析' % (done, args.rounds, '、'.join(palaces)))
        sys.exit(2)

    script = build_script(open(dispatch, encoding='utf-8').read(), palaces, reasons, n)
    out = os.path.join(batch_dir, 'refill_%d.workflow.js' % n)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(script)
    print('已生成第 %d 轮补发脚本：%s（FAIL 宫：%s）' % (n, out, '、'.join(palaces)))
    print('后台执行后重跑 check_outputs 复核；仍 FAIL 且未到 %d 轮封顶则再跑本脚本' % args.rounds)


if __name__ == '__main__':
    main()
