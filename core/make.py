# -*- coding: utf-8 -*-
"""紫微斗数分析一条龙入口（make.py）

把旧三步串成一条命令（编排层零侵入：不改 paipan.js / retrieve.py / prep_inputs.py
本体，旧三步原样可用）：
  排盘 node engine/paipan.js       --birth/--gender --out <outdir>/pan.json（--pan 模式跳过）
  检索 python core/retrieve.py     --pan <outdir>/pan.json --out <outdir>/ctx.json
  生成 python core/prep_inputs.py  --pan <outdir>/pan.json --ctx <outdir>/ctx.json --outdir <outdir>

子进程一律文件中转取结果（沙箱环境 named-pipe EPERM 兼容：stdout 落 DEVNULL、
stderr 继承直出，禁管道捕获）；pan.json/ctx.json 留在 outdir 内，与 12 份 inputs
同目录自包含，可直接取用。

用法：
  python make.py --birth "1995-06-15 12:30" --gender male --outdir <dir>
  python make.py --pan pans/<命主名>.json --outdir <dir>
  python make.py --birth "..." --gender male --save-pan pans/pan_xxx.json --outdir <dir>
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIPAN_JS = os.path.join(SKILL_ROOT, 'engine', 'paipan.js')
RETRIEVE_PY = os.path.join(SKILL_ROOT, 'core', 'retrieve.py')
PREP_INPUTS_PY = os.path.join(SKILL_ROOT, 'core', 'prep_inputs.py')


def _anchors():
    """逐级向上找 anchors.json（目录内直放或 extensions 下），env 同名键覆盖；
    找不到返回 None（开源环境软依赖，调用方自决落点）。"""
    import json as _json
    p = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        cand = None
        c = os.path.join(p, "anchors.json")
        if os.path.exists(c):
            cand = c
        else:
            f = os.path.join(p, "extensions", "anchors.json")
            if os.path.exists(os.path.join(p, "extensions")) and os.path.exists(f):
                cand = f
        if cand:
            with open(c, encoding="utf-8") as fh:
                d = _json.load(fh)
            return {k: os.environ.get(k, v) for k, v in d.items()}
        np_ = os.path.dirname(p)
        if np_ == p:
            break
        p = np_
    return None


PERSON_RE = re.compile(r'^[\w\u4e00-\u9fff-]+$')   # 对象名白名单（防路径注入）
TOPIC_RE = re.compile(r'^[A-Za-z]+$')              # 主题词白名单（同上）
PAN_NAME_RE = re.compile(r'^pan_\d{8}-\d{4}_(male|female)\.json$')   # pans/ 命名规约
INPUT_RE = re.compile(r'^input_\d{2}_.+\.md$')
DISPATCH_TPL = os.path.join(SKILL_ROOT, 'bin', 'dispatch_12palaces.workflow.js')


def _zero_root():
    """anchors 在场时的 ZERO_ROOT，缺席返回 None"""
    anc = _anchors()
    return (anc or {}).get('ZERO_ROOT') if anc else None


def _ensure_output_gitignore(base):
    """开源落点 {技能根}\\output 首建时写 .gitignore（忽略全部产物）"""
    gi = os.path.join(base, '.gitignore')
    if not os.path.exists(gi):
        os.makedirs(base, exist_ok=True)
        with open(gi, 'w', encoding='utf-8', newline='\n') as f:
            f.write('*\n!.gitignore\n')


def resolve_outdir(user_outdir, person=None, topic=None):
    """定输出目录三级链：
    ① --outdir 显式指定→原样用；
    ② --person+--topic→anchors 在场 {ZERO_ROOT}\\output\\output\\{person}\\{topic}\\temp\\
       （原局平铺唯一源，不套时间戳子目录，重做=同名覆盖零清理），
       缺席落 {技能根}\\output\\{person}\\{topic}\\temp\\（首建写 .gitignore）；
    ③ 都不带→缺省 .dsh-tmp\\ziwei_{ts}（anchors 缺落 output\\ziwei_{ts}）。
    创建/探写遇 PermissionError/OSError 自动改落 %TEMP%\\ziwei_{ts}。返回 (目录, 是否本次新建)。"""
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    if user_outdir:
        primary = os.path.abspath(user_outdir)
    else:
        zero_root = _zero_root()
        if person and topic:
            if zero_root:
                primary = os.path.join(zero_root, 'output', 'output',
                                       person, topic, 'temp')
            else:
                _ensure_output_gitignore(os.path.join(SKILL_ROOT, 'output'))
                primary = os.path.join(SKILL_ROOT, 'output', person, topic, 'temp')
        else:
            if zero_root:
                primary = os.path.join(zero_root, '.dsh-tmp', f'ziwei_{ts}')
            else:
                _ensure_output_gitignore(os.path.join(SKILL_ROOT, 'output'))
                primary = os.path.join(SKILL_ROOT, 'output', f'ziwei_{ts}')
    fallback = os.path.join(tempfile.gettempdir(), f'ziwei_{ts}')
    for d in (primary, fallback):
        try:
            created = not os.path.exists(d)
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, '.write_probe')
            with open(probe, 'w', encoding='utf-8'):
                pass
            os.remove(probe)
            if d == fallback:
                print(f'目标目录不可写，已改落：{d}')
            return d, created
        except OSError as e:
            print(f'目录不可写：{d}（{e}）')
    raise RuntimeError(f'输出目录均不可写：{primary} / {fallback}')


def run_step(title, cmd):
    """跑一步子进程：stdout 落 DEVNULL（结果一律从文件取），stderr 继承直出"""
    print(f'── {title}')
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f'{title}失败（退出码 {proc.returncode}，上游错误见上方输出）')


def generate_dispatch(outdir, pan_path):
    """--person 模式收尾件：读 dispatch 模板，替换占位符后落 <outdir>\\dispatch.workflow.js。
    路径占位符反斜杠双写（JS 字符串字面量转义）。"""
    with open(pan_path, 'r', encoding='utf-8') as f:
        pan = json.load(f).get('pan', {})
    zhi_to_gong = pan.get('twelvePalaces', {}) or {}

    def gong_name(zhi):
        name = zhi_to_gong.get(zhi, zhi)
        return name if name.endswith('宫') else name + '宫'

    parts = []
    for hua in ('禄', '权', '科', '忌'):
        info = (pan.get('siHua', {}) or {}).get(hua) or {}
        gong = info.get('gong', '?')
        parts.append(f"化{hua}{info.get('star', '?')}@{gong}（{gong_name(gong)}）")
    sihua_line = '、'.join(parts)
    gender_cn = {'male': '男', 'female': '女'}.get(pan.get('gender', ''), '男')
    shen_zhi = (pan.get('mingShen', {}) or {}).get('shen', '')
    shengong_palace = gong_name(shen_zhi) if shen_zhi else ''

    with open(DISPATCH_TPL, 'r', encoding='utf-8') as f:
        tpl = f.read()
    js_dir = outdir.replace('\\', '\\\\')
    content = (tpl.replace('{{INPUTS_DIR}}', js_dir)
                  .replace('{{OUTPUTS_DIR}}', js_dir)
                  .replace('{{SIHUA_LINE}}', sihua_line)
                  .replace('{{GENDER}}', gender_cn)
                  .replace('{{SHENGONG_PALACE}}', shengong_palace))
    dest = os.path.join(outdir, 'dispatch.workflow.js')
    with open(dest, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f'workflow 脚本已生成：{os.path.abspath(dest)}，直接以其内容执行')


def cleanup(outdir, created):
    """出错清理本次产物：pan.json/ctx.json/input_*.md；本次自建的目录清空后一并删除"""
    try:
        for name in os.listdir(outdir):
            if name in ('pan.json', 'ctx.json') or INPUT_RE.match(name):
                os.remove(os.path.join(outdir, name))
        if created:
            os.rmdir(outdir)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(
        description='紫微斗数分析一条龙：排盘→检索→分宫输入生成（旧三步合一）')
    ap.add_argument('--birth', help='生辰 "YYYY-MM-DD HH:mm"（与 --pan 二选一）')
    ap.add_argument('--gender', choices=['male', 'female'], default='male',
                    help='性别（默认 male，同 paipan.js）')
    ap.add_argument('--pan', help='已有命盘 JSON 路径（paipan.js 输出同构；与 --birth 二选一）')
    ap.add_argument('--save-pan', help='排盘结果另存路径（仅 --birth 模式；pans/ 下须合命名规约）')
    ap.add_argument('--outdir', default=None,
                    help='输出目录（缺省 <ZERO_ROOT>\\.dsh-tmp\\ziwei_<时间戳>（取 anchors.json），不可写自动改落 %%TEMP%%）')
    ap.add_argument('--person', default=None,
                    help='分析对象名（与 --topic 搭配：outdir 落 output\\output\\<person>\\<topic>\\temp\\ 平铺唯一源，重做=同名覆盖）')
    ap.add_argument('--topic', default=None,
                    help='主题词，仅英文字母（与 --person 搭配，防路径注入）')
    ap.add_argument('--kb', choices=['open'], default=None,
                    help='知识库标识，默认 open；环境变量 ZIWEI_KB 备选）')
    args = ap.parse_args()

    if bool(args.birth) == bool(args.pan):
        ap.error('--birth 与 --pan 必须二选一')
    if bool(args.person) != bool(args.topic):
        ap.error('--person 与 --topic 须同时提供')
    if args.person and not PERSON_RE.match(args.person):
        print(f'错误：--person 含非法字符（只允中文/字母/数字/下划线/连字符）：{args.person}',
              file=sys.stderr)
        sys.exit(1)
    if args.topic and not TOPIC_RE.match(args.topic):
        print(f'错误：--topic 须为纯英文字母：{args.topic}', file=sys.stderr)
        sys.exit(1)
    if args.save_pan and not args.birth:
        ap.error('--save-pan 仅与 --birth 搭配（--pan 模式盘文件已存在）')

    if args.birth:
        node = shutil.which('node')
        if not node:
            print('错误：未找到 node——engine/paipan.js 排盘需要 Node.js。\n'
                  '请安装 Node.js 或检查 PATH 后重试；已有盘文件可用 --pan 模式跳过排盘。',
                  file=sys.stderr)
            sys.exit(2)

    outdir, created = resolve_outdir(args.outdir, args.person, args.topic)
    print(f'输出目录：{outdir}')
    pan_path = os.path.join(outdir, 'pan.json')
    ctx_path = os.path.join(outdir, 'ctx.json')

    try:
        if args.birth:
            run_step(f'排盘 paipan.js --birth "{args.birth}" --gender {args.gender}',
                     [node, PAIPAN_JS, '--birth', args.birth,
                      '--gender', args.gender, '--out', pan_path])
        else:
            src = os.path.abspath(args.pan)
            if not os.path.isfile(src):
                raise RuntimeError(f'命盘文件不存在：{src}')
            print(f'── 载入命盘 {src}')
            shutil.copyfile(src, pan_path)

        retrieve_cmd = [sys.executable, RETRIEVE_PY, '--pan', pan_path, '--out', ctx_path]
        if args.kb:
            retrieve_cmd += ['--kb', args.kb]
        run_step(f'检索 retrieve.py（十二宫知识库切片，kb={args.kb or "默认"}）', retrieve_cmd)
        run_step('生成 prep_inputs.py（12 份分宫输入）',
                 [sys.executable, PREP_INPUTS_PY,
                  '--pan', pan_path, '--ctx', ctx_path, '--outdir', outdir])

        if args.save_pan:
            dest = os.path.abspath(args.save_pan)
            if (os.path.basename(os.path.dirname(dest)) == 'pans'
                    and not PAN_NAME_RE.match(os.path.basename(dest))):
                print(f'警告：{dest} 不合 pans/ 命名规约 '
                      f'pan_<YYYYMMDD-HHmm>_(male|female).json（仍照常保存）')
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(pan_path, dest)
            print(f'命盘已另存：{dest}')
    except (RuntimeError, OSError) as e:
        cleanup(outdir, created)
        print(f'错误：{e}\n本次临时产物已清理。', file=sys.stderr)
        sys.exit(1)

    inputs = sorted(n for n in os.listdir(outdir) if INPUT_RE.match(n))
    print(f'\n完成：{len(inputs)} 份分宫输入 + pan.json + ctx.json（自包含） -> {outdir}')
    for n in inputs:
        print(f'  {n}\t{os.path.getsize(os.path.join(outdir, n))} bytes')

    if args.person:
        # 历史印证一查多注：原局 combo → FAISS top-K → 类别路由宫位注入
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin'))
            import verify_refs
            with open(pan_path, 'r', encoding='utf-8') as f:
                pan_data = json.load(f).get('pan', {})
            # 脱敏比对用账本权威名（盘文件名）：报告对象名与账本权威名字符串不等会把自己的历史错脱敏；
            # pan_path 是批次内拷贝的 pan.json，须取源盘名（--birth 排盘无名，留空=全部按跨命主脱敏）
            src_pan = os.path.abspath(args.pan) if args.pan else pan_path
            ledger_person = os.path.splitext(os.path.basename(src_pan))[0]
            verify_refs.inject_verify_refs(outdir, verify_refs.origin_combo(pan_data),
                                           ledger_person)
        except Exception as e:  # 容错：印证链失败不阻断生成
            print(f'⚠ 历史印证注入失败（{e}）——批次照常生成')
        generate_dispatch(outdir, pan_path)
        print(f'最终输出目录：{os.path.abspath(outdir)}')


if __name__ == '__main__':
    main()
