# -*- coding: utf-8 -*-
"""事件归宫自动建议：事件文本关键词匹配映射表 → 建议宫位+置信度。
脚本兜底 80% 常规案例，匹配不到的边缘案例交 AI 判断。映射表条目=常用归宫映射。
用法：suggest_palace.py --text "事件描述"
"""
import argparse
import sys

# 关键词 → (建议宫位, 备选宫位)；条目=常用归宫映射
PALACE_KEYWORDS = [
    (('师父', '师长', '长辈', '上司'), '父母宫', ''),
    (('同辈', '朋友', '合作伙伴'), '兄弟宫', '仆役宫'),
    (('服务人员', '物业', '快递', '销售', '维修'), '仆役宫', ''),
    (('下属', '晚辈'), '仆役宫', ''),
    (('配偶', '恋人', '伴侣'), '夫妻宫', ''),
    (('子女', '学生', '弟子'), '子女宫', ''),
    (('股票', '期货', '交易', '投资'), '财帛宫', ''),
    (('签约', '合同', '文书'), '官禄宫', ''),
]


def suggest(text):
    """→ [(建议宫位, 命中关键词表, 置信度, 备选)]；置信度=命中条目数（1=高，≥2=中·多域）。"""
    out = []
    for kws, palace, alt in PALACE_KEYWORDS:
        hit = [k for k in kws if k in text]
        if hit:
            out.append((palace, hit, '高', alt))
    return out


def main():
    ap = argparse.ArgumentParser(description='事件归宫自动建议（关键词映射表兜底）')
    ap.add_argument('--text', required=True, help='事件描述文本')
    args = ap.parse_args()
    hits = suggest(args.text)
    if not hits:
        print('建议宫位: 无（关键词未命中——交 AI 按映射表判断）')
        return
    confidence = '高' if len(hits) == 1 else '中（多域命中，须按事件主体裁决）'
    for palace, kws, _, alt in hits:
        line = '建议宫位: %s (匹配关键词: %s, 置信度: %s)' % (palace, '、'.join(kws), confidence)
        if alt:
            line += ' [备选: %s]' % alt
        print(line)


if __name__ == '__main__':
    sys.exit(main())
