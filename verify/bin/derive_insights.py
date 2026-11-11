# -*- coding: utf-8 -*-
"""实测条目管道。用法：
derive_insights.py [--data-dir 目录] [--out-dir 目录] [--min-n 10]
    扫账本按 L2 键（应验宫 event_palace：宫名×星系×象别照入）与 L3 键（应验宫星系×象别，
    不论宫名）聚合（单宫记键）；某结构 n≥--min-n 时生成实测条目候选 md 落 insights_pending\
（目录自动建；同结构重复生成覆盖=幂等）。零第三方依赖。
derive_insights.py --collect-revise <批次目录> [--data-dir 目录]
    扫批次全部 output_*.md 的「参考表态」（## 参考表态 节或含 采信/反驳 的行），
逐条追加 _verify\revise_log.jsonl（date/palace/stance/reason/source_batch）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SKILL_ROOT, 'core'))
sys.path.insert(0, os.path.join(SKILL_ROOT, 'bin'))
from common import list_shards, out, read_lines, resolve_data_dir  # noqa: E402
import verify_refs  # noqa: E402

PRED_OK = '预测准确'
PRED_BAD = '预测不准'
DEFAULT_OUT_SUBDIR = 'insights_pending'
STANCE_RE = re.compile(r'(采信|部分采信|反驳)')


def default_out_dir():
    return os.path.join(resolve_data_dir(None), DEFAULT_OUT_SUBDIR)


def iter_records(data_dir):
    for _, _, name in list_shards(data_dir):
        for line in read_lines(os.path.join(data_dir, name)):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            yield rec


def key_label(kind, key):
    """干支直查制：三层键均为干支两元组。"""
    if kind == '盘型级':
        return '盘型级 %s%s日' % key
    if kind == '星系级':
        return '星系级 %s日·应验宫@%s' % key
    return '宫位级 %s日·应验宫@%s' % key


def key_fp(kind, key):
    h = hashlib.md5(json.dumps([kind, [str(x) if not isinstance(x, frozenset) else sorted(x)
                                       for x in (key if isinstance(key, tuple) else (key,))]],
                               ensure_ascii=False, sort_keys=True, default=list).encode('utf-8'))
    return h.hexdigest()[:12]


def is_first_evidence(rec):
    return bool(rec.get('prediction')) and rec.get('verify_result') in (PRED_OK, PRED_BAD)


def derive(data_dir, out_dir, min_n):
    groups = {}
    for rec in iter_records(data_dir):
        for kind, keys in (('盘型级', verify_refs.record_panxing_keys(rec)),
                           ('星系级', verify_refs.record_xingxi_keys(rec)),
                           ('宫位级', verify_refs.record_gongwei_keys(rec))):
            for key in keys:
                groups.setdefault((kind, key), []).append(rec)
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for (kind, key), recs in sorted(groups.items(), key=lambda t: key_label(*t[0])):
        if len(recs) < min_n:
            continue
        first = [r for r in recs if is_first_evidence(r)]
        second = [r for r in recs if not is_first_evidence(r)]
        cats = {}
        for r in recs:
            cats[r.get('category', '')] = cats.get(r.get('category', ''), 0) + 1
        lines = ['# 实测条目候选：%s' % key_label(kind, key),
                 '',
                 '- 样本量：%d（一等证据 %d / 二等证据 %d）'
                 % (len(recs), len(first), len(second)),
                 '- 结构：`%s`' % json.dumps(
                     [sorted(x) if isinstance(x, frozenset) else x for x in key],
                     ensure_ascii=False),
                 '- 事件分布：%s' % '、'.join('%s×%d' % kv for kv in
                                               sorted(cats.items(), key=lambda t: -t[1])),
                 '',
                 '## 事件清单（日期｜类别｜预测→结果｜证据等级）',
                 '']
        for r in sorted(recs, key=lambda r: r.get('event_date', '')):
            chain = '→'.join(p for p in (r.get('prediction', ''), r.get('outcome', '')) if p) \
                or '（无预测——事件关联）'
            lines.append('- %s｜%s｜%s｜%s' % (
                r.get('event_date', ''), r.get('category', ''), chain,
                '一等' if is_first_evidence(r) else '二等'))
        lines += ['', '> 待用户审核：通过后并入分析语料层（知识库理论+库内实测双源呈现）。',
                  '> 生成：derive_insights.py（幂等覆盖；闸门 n≥%d）' % min_n, '']
        path = os.path.join(out_dir, 'insight-%s-%s.md' % (kind, key_fp(kind, key)))
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines))
        made.append((key_label(kind, key), len(recs), path))
    out('聚合 %d 个结构键；n≥%d 生成候选 %d 份 → %s'
        % (len(groups), min_n, len(made), out_dir))
    for label, n, path in made:
        out('  %s（n=%d）：%s' % (label, n, os.path.basename(path)))
    return len(made)


def collect_revise(batch_dir, data_dir):
    log_path = os.path.join(resolve_data_dir(data_dir), 'revise_log.jsonl')
    existing = 0
    if os.path.isfile(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            existing = sum(1 for ln in f if ln.strip())
    batch_date = os.path.basename(os.path.abspath(batch_dir).rstrip('\\/'))
    added = []
    for path in sorted(glob.glob(os.path.join(batch_dir, 'output_*.md'))):
        m = re.match(r'^output_\d+_(.+)\.md$', os.path.basename(path))
        palace = m.group(1) if m else ''
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # 取「## 参考表态」节；无节标题则退而扫含表态词的行
        in_sec = False
        for ln in lines:
            if ln.startswith('## '):
                in_sec = '参考表态' in ln
                continue
            if not in_sec and not STANCE_RE.search(ln):
                continue
            if not in_sec and ln.lstrip().startswith(('>', '#')):
                continue
            sm = STANCE_RE.search(ln)
            if not sm:
                continue
            reason = re.sub(r'^[\s>*\-\d\.、()]*', '', ln.strip())
            reason = STANCE_RE.sub('', reason, count=1).strip('：:——- \t')
            added.append({
                'date': batch_date,
                'palace': palace,
                'stance': sm.group(1),
                'reason': reason,
                'source_batch': os.path.abspath(batch_dir),
            })
    if added:
        with open(log_path, 'a', encoding='utf-8', newline='\n') as f:
            for rec in added:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    out('参考表态采集：新增 %d 条（原日志 %d 条）→ %s' % (len(added), existing, log_path))
    for rec in added:
        out('  %s %s：%s——%s' % (rec['date'], rec['palace'], rec['stance'], rec['reason']))
    return len(added)


def main():
    ap = argparse.ArgumentParser(description='实测条目管道（候选生成+表态采集）')
    ap.add_argument('--data-dir', dest='data_dir', default=None)
    ap.add_argument('--out-dir', dest='out_dir', default=None,
                    help='候选 md 输出目录（默认数据目录下 insights_pending）')
    ap.add_argument('--min-n', dest='min_n', type=int, default=10,
                    help='实测条目闸门（默认 10）')
    ap.add_argument('--collect-revise', dest='collect_revise', default=None,
                    metavar='批次目录', help='扫批次 output_*.md 参考表态 → revise_log.jsonl')
    args = ap.parse_args()

    if args.collect_revise:
        if not os.path.isdir(args.collect_revise):
            out('错误：批次目录不存在：%s' % args.collect_revise)
            sys.exit(2)
        collect_revise(args.collect_revise, args.data_dir)
        return
    derive(resolve_data_dir(args.data_dir),
            args.out_dir or default_out_dir(), args.min_n)


if __name__ == '__main__':
    main()
