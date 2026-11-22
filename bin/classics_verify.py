#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""古籍引文验证（典籍三工具件之一，方案 v1.9.2 批）。

功能：--quote 引文片段 → --book 书名匹配 data/classics/<书名>.txt（缺省=全库扫）→ 五层容错逐级尝试：
  ①逐字 ②空白归一（去空格/全角空格/Tab）③繁简等价（三级加载：opencc 库→包内词典 data/opencc_ts_characters.txt→内置映射表）
  ④跨行拼接（去换行比对，命中报行号区间）⑤虚词差异（之乎者也矣焉哉可跳，正则可选字）
命中：exit 0 + 书名 + 行号；全败：exit 1 + 各层最近差异摘要。

用法：
  python classics_verify.py --quote "学而时习之" --book "论语"
  python classics_verify.py --quote "欲速则不达"            # 全库扫
零第三方依赖（opencc 为可选增强）；PYTHONUTF8=1 兼容。
"""
import argparse
import difflib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSICS_DIR = os.path.normpath(os.path.join(HERE, "..", "data", "classics"))

# 内置繁→简常用映射表（opencc 不可用时的轻量版；"繁简 繁简"配对串解析）
_T2S_PAIRS = (
    "萬万 與与 東东 絲丝 兩两 嚴严 單单 豐丰 為为 舉举 義义 樂乐 習习 書书 買买 爭争 於于 "
    "虧亏 雲云 亞亚 產产 畝亩 親亲 億亿 僅仅 從从 倫伦 們们 價价 眾众 優优 會会 傳传 傷伤 "
    "體体 餘余 傭佣 倆俩 儉俭 債债 傾倾 兒儿 兌兑 蘭兰 關关 興兴 養养 內内 冊册 寫写 車车 "
    "軍军 農农 決决 況况 凍冻 淨净 涼凉 減减 幾几 鳳凤 擊击 劃划 則则 剛刚 創创 刪删 別别 "
    "劑剂 劍剑 勸劝 辦办 務务 動动 勵励 勞劳 勢势 區区 醫医 华华 賣卖 盧卢 衛卫 卻却 廠厂 "
    "厲厉 壓压 厭厌 縣县 參参 雙双 發发 變变 葉叶 號号 歎叹 聽听 問问 間间 閑闲 東东 板板 "
    "極极 轉转 輪轮 輕轻 較较 載载 輔辅 輛辆 輸输 辨辨 辦办 辭辞 邊边 還还 這这 進进 遠远 "
    "運运 過过 適适 選选 遺遗 錯错 錄录 錢钱 錦锦 鍾钟 鍵键 長长 門门 開开 閉闭 問问 關关 "
    "陽阳 陰阴 隆隆 階阶 隨随 難难 雲云 電电 需需 靜静 頂顶 項项 順顺 須须 顧顾 風风 飛飞 "
    "養养 飯饭 飲饮 馬马 駕驾 骨骨 體体 高高 齊齐 義义 美美 聞闻 膽胆 舉举 艦舰 良良 艱艰 "
    "色色 花花 芳芳 若若 苦苦 英英 帶带 度度 庭庭 康康 廣广 應应 開开 歷历 歸归 當当 里里 "
    "玄玄 玉玉 王王 現现 理理 甚甚 生生 用用 田田 由由 疾疾 發发 皇皇 盡尽 監监 真真 睿睿 "
    "禮礼 禍祸 禎祯 禮礼 禪禅 種种 稱称 穀谷 空空 立立 童童 端端 競竞 篤笃 簡简 算算 精精 "
    "純纯 納纳 紅红 約约 級级 紛纷 素素 紡纺 索索 紫紫 結结 絕绝 統统 経经 絲丝 給给 絳绛 "
    "維维 網网 經经 綱纲 網网 緊紧 緒绪 線线 緣缘 編编 緩缓 練练 緯纬 確确 縱纵 總总 縣县 "
    "聖圣 聞闻 聲声 職职 聯联 肅肃 膠胶 興兴 舉举 艦舰 艱艰 華华 萬万 萬万 葉叶 著着 蒙蒙 "
    "慮虑 競竞 應应 斷断 無无 煙烟 熱热 熟熟 燈灯 營营 燕燕 爺爷 爾尔 牆墙 牘牍 獲获 狀状 "
    "獻献 玄玄 率率 玉玉 王王 環环 現现 琴琴 瑤瑶 見见 規规 視视 親亲 覺觉 覽览 觀观 觶觞 "
    "言言 訓训 記记 訐讦 討讨 讓让 訕讪 訖讫 訓训 訝讶 訟讼 訣诀 訪访 設设 許许 訴诉 診诊 "
    "詐诈 詞词 詔诏 評评 詛诅 認认 誓誓 誡诫 語语 誤误 誥诰 誦诵 誨诲 說说 請请 諸诸 諾诺 "
    "讀读 讖谶 谷谷 豈岂 豐丰 象象 負负 貢贡 財财 責责 賢贤 賬账 質质 贈赠 趨趋 趣趣 跡迹 "
    "路路 身身 車车 軍军 軌轨 軒轩 轉转 輕轻 較较 載载 輔辅 辦办 辭辞 邊边 還还 這这 進进 "
    "道道 遠远 遭遭 適适 遲迟 選选 遺遗 避避 邀邀 還还 邏逻 邁迈 醫医 釋释 重量 鉤钩 銓诠 "
    "銀银 銅铜 錢钱 錦锦 鍵键 鎖锁 鎮镇 鏡镜 鐘钟 鐵铁 鑑鉴 長长 門门 開开 閉闭 問问 閒闲 "
    "間间 閱阅 防防 陽阳 隆隆 隊队 階阶 隨随 隱隐 難难 雲云 電电 震震 霖霖 霜霜 靈灵 青青 "
    "靜静 非非 面面 革革 韓韩 頂顶 項项 順顺 須须 頭头 頻频 題题 顆颗 題题 顏颜 願愿 類类 "
    "顧顾 風风 飛飞 餐餐 飯饭 飲饮 養养 餘余 館馆 首首 香香 馬马 駐驻 駕驾 骨骨 體体 高高 "
    "鳥鸟 鳴鸣 鳳凤 龍龙 龜龟 "
    + "學学 時时 說说 話话 課课 誰谁 誰谁 滿满 漢汉 潛潜 潔洁 無无 煩烦 燒烧 樂乐 徑径 復复 徵征 志志 念念 思思 怨怨 怒怒 恨恨 恩恩 恭恭 慕慕 慳悭 擊击 擔担 據据 操操 支支 攻攻 放放 政政 敗败 敢敢 散散 敬敬 數数 鬥斗 料料 斜斜 断断 斯斯 新新 於于 旁旁 旅旅 旣既 旧旧 昔昔 昨昨 昭昭 晉晋 晒晒 晚晚 智智 暂暂 暴暴 服服 望望 朝朝 期期 木木 未未 本本 术术 朱朱 樸朴 乖乖 乘乘 事事 二二 云云 五五 井井 亙亘 一些 亂乱 亞亚 亡亡 交交 亦亦 产产 享享 京京 亭亭 亮亮 人人 仁仁 什什 今今 介介 仍仍 从从 仄仄 乏乏 元元 兄兄 充充 先光 克克 免免 兒儿 入入 全全 八八 六六 具具 典典 兼兼 内内 册册 再再 冒冒 冠冠 冬冬 冰冰 冲冲 决决 况况 冷冷 准准 淺浅 清清 減减 減减 渺渺 湖湖 源源 準准 滅灭 滄沧 滿满 漂漂 演演 潜潜 火火 灯灯 灰灰 災灾 爐炉 爲为 爵爵 牌牌 牙牙 牛牛 犬犬 玄玄 玉玉 王王 环环 珠珠 班班 現现 理理 琴琴 瑞瑞 瑣琐 瑾瑾 璧璧 甫甫 甫畝 画画 畧略 蔬蔬 藏藏 虎虎 處处 號号 虛虚 蠢蠢 衣衣 表表 裁裁 補补 裝装 西西 要要 見见 規规 覆覆 見见 觀观 觚觚 觴觞 言言 訂订 訃讣 計计 訊讯 訛讹 訝讶 社社 祖祖 神神 祥祥 祸祸 禎祯 禮礼 禹禹 秋秋 种种 科科 秒秒 秘秘 租租 秦秦 秩秩 称称 移移 稽稽 穆穆 穹穹 空空 立立 竑纮 步步 涉涉 洋洋 洛洛 洞洞 津津 派派 流流 浮浮 浪浪 海海 消消 涉涉 深深 淵渊 混混 淹淹 添添  clearclear 爲为 疑疑 疏疏 疲疲 疾疾 病病 痒痒 痕痕 發发 皇皇 盈盈 益益 盛盛 相相 盜盗 盼盼 益益 盡尽 監监 盧卢 眠眠 着着 督督 睿睿 瞬瞬 知知 石石 碎碎 碑碑 磊磊 祕秘 福福 積积 窮穷 竊窃 竟竟 章章 端端 笑笑 筆笔 算算 糧粮 精精 糟糟 系系 素素 索索 累累 細细 純纯 納纳 紅红 級级 紛纷 紙纸 級级 素素 紡纺 索索 純纯 素素 緊紧 緻致 總总 縱纵 縮缩 繁繁 織织 缮缮 美美 群群 羨羡 義义 習习 翔翔 翻翻 老老 考考 者者 耕耕 耗耗 耳耳 聿聿 育育 肅肃 肆肆 肢肢 肯肯 育育 肺肺 背背 胡胡 背背 胥胥 舒舒 舍舍 良良 色色 艱艰 芝芝 花花 芳芳 芽芽 若若 苦苦 英英 茲兹 草草 荒荒 莊庄 書书 易易 昌昌 昆昆 明明 昏昏 易易 星星 春春 昨昨 昭昭 是是 顯显 晉晋 息息 悅悦 悔悔 悟悟 悲悲 惠惠 惡恶 惧惧 想想 愉愉 意意 愚愚 愛爱 感感 慈慈 慕慕 慢慢 慣惯 慶庆 憂忧 憲宪 應应 舊旧 見见 覆覆 訊讯 訥讷 訪访 設设 許许 診诊 詐诈 詞词 該该 詳详 語语 誤误 誥诰 誦诵 誨诲 說说 請请 諸诸 諾诺 讀读 變变 讓让 谷谷 豐丰 象象 負负 貢贡 財财 責责 賢贤 賓宾 賜赐 賬账 質质 贈赠 趨趋 趣趣 路路 身身 車车 軍军 軌轨 軒轩 軟软 轉转 輕轻 較较 載载 輔辅 輸输 辞辞 辨辨 辦办 辭辞 返返 迎迎 近近 返返 余余 來来 侯侯 便便 係系 促促 俄俄 俗俗 保保 修修 個个 們们 倒倒 候候 倚倚 借借 倡倡 值值 倾倾 假假 停停 偏偏 做做 健健 側侧 偶偶 偷偷 傅傅 傷伤  richrich 傳传 傲傲 催催 僅仅 像像 僑侨 價价 儀仪 億亿 儒儒 儔俦 允允 元元 兄兄 先先 光光 克克 免免 兒儿 兔兔 入入 內内 兩两 八八 公公 六六 兰兰 共共 關关 兴兴 兵兵 其其 具具 典典 兹兹 再再 冒冒 冠冠 冬冬 冷冷 准准 净净 凉凉 减减 几几 凤凤 凭凭 出出 击击 凿凿 刀刀 分分 切切 划划 則则 刚刚 创创 删删 别别 刭刭 刽刽 刿刿 剀剀 剂剂 剑剑 剐剐 剧剧 劝劝 办办 务务 劣劣 动动 助助 努努 劫劫 励励 劲劲 劳劳 势势 勋勋 勤勤 勰勰 勺勺 勿勿 匀匀 包包 匆匆 匈匈 化化 北北 医医 匿匿 十十 千千 升升 午午 半半 卑卑 卒卒 卓卓 南南 卫卫 厂厂 厅厅 历历 厉厉 压压 厌厌 厓厓 厕厕 厚厚 原原 厦厦 厨厨 厩厩 县县 参参 又又 双双 反反 取取 受受 变变 叙叙 叠叠 口口 古古 句句 另另 叫叫 召召 可可 台台 史史 右右 号号 司司 叶叶 吃吃 各各 合合 同同 名名 后后 吐吐 向向 吓吓 吕吕 吗吗 吁吁 吃吃 各各 否否 君君 吝吝 吞吞 吟吟 吠吠 否否 含含 听听 启启 吴吴 吾吾 呀呀 呆呆 呈呈 告告 呕呕 员员 呵呵 呼呼 命命 咏咏 咸咸 哀哀 品品 哇哇 哈哈 哉哉 响响 哑哑 哔哔 哦哦 哭哭 哲哲 唇唇 唐唐 唬唬 售售 唯唯 唱唱 商商 啊啊 啥啥 啦啦 善善 喇喇 喊喊 喏喏 喜喜 喝喝 喵喵 喟喟 喘喘 喬乔 单单 呜呜 喂喂 善善 喻喻 嗚呜 嗜嗜 嗡嗡 嗣嗣 嗯嗯 嗽嗽 嘈嘈 嘛嘛 嘴嘴 嘻嘻 器器 嚕噜 囉啰 囚囚 四四 回回 因因 团团 囤囤 园园 困困 围围 固固 国国 图图 圆圆 圈圈 土土 在在 地地 圭圭 圾圾 址址 均均 坎坎 坏坏 坐坐 块块 坚坚 坛坛 坜坜 坝坝 坟坟 垂垂 垒垒 垚垚 垩垩 垭垭 型型 垣垣 垫垫 城城 埒埒 埏埏 埔埔 域域 執执 培培 基基 埼埼 堂堂 堆堆 堕堕 堵堵 塗涂 填填 塵尘 壇坛 士士 壬壬 壯壮 声声 壳壳 壶壶 壹壹 夂夂 处处 备备 复复 夥伙 失失 头头 夷夷 夸夸 夹夹 夺夺 夼夼 奇奇 奈奈 奉奉 奋奋 奏奏 契契 奔奔 奖奖 奏奏 套套 奠奠 奡奡 奢奢 女女 奴奴 奶奶 奸奸 她她 好好 妁妁 如如 妃妃 妄妄 妆妆 妇妇 妈妈 姗姗 姑姑 始始 姐姐 妹妹 妻妻 姻姻 娉娉 娜娜 娥娥 娘娘 娛娱 婦妇 婆婆 婚婚 婢婢 婶婶 媒媒 媚媚 嫁嫁 嫉嫉 嫌嫌 嫩嫩 嬰婴 孀孀 孀孀 子子 孔孔 孕孕 字字 存存 孙孙 孜孜 孝孝 季季 孤孤 孩孩 学学 孺孺 宇宇 守守 安安 完完 宗宗 官官 客客 宣宣 室室 宫宫 宪宪 害害 宴宴 家家 容容 宽宽 宾宾 宿宿 寂寂 寄寄 密密 寇寇 寅寅 寝寝 察察 寡寡 寡寡 寨寨 審审 寫写 寬宽 寝寝 寞寞 察察 寡寡 實实 寧宁 審审 寨寨 審审 寫写 专专 且且 世世 丙丙 业业 丛丛 东东 丝丝 丢丢 两两 严严 丧丧 个个 丰丰"
)
T2S_TABLE = {}
for _p in _T2S_PAIRS.split():
    if len(_p) >= 2 and _p[0] != _p[1] and not _p[0].isascii() and not _p[1].isascii():
        T2S_TABLE[ord(_p[0])] = _p[1]

FUNC_WORDS = set("之乎者也矣焉哉")


TS_DICT_PATH = os.path.normpath(os.path.join(HERE, "..", "data", "opencc_ts_characters.txt"))


def load_ts_dict():
    """②包内词典级：data/opencc_ts_characters.txt（TSV：繁\t简）建字映射。"""
    table = {}
    with open(TS_DICT_PATH, encoding="utf-8") as f:
        for ln in f:
            parts = ln.rstrip("\r\n").split("\t")
            if len(parts) >= 2 and len(parts[0]) == 1 and len(parts[1]) == 1:
                table[ord(parts[0])] = parts[1]
    if len(table) < 100:  # 残缺词典不半用，退③
        raise ValueError(f"词典对数异常：{len(table)}")
    return (lambda text: text.translate(table)), len(table)


def load_converter():
    """三级繁简转换加载：①opencc库 ②包内词典 ③内置映射表；逐级降退不炸。"""
    try:
        import opencc  # type: ignore

        return opencc.OpenCC("t2s").convert, "opencc库"
    except Exception:
        pass
    try:
        convert, pairs = load_ts_dict()
        return convert, f"包内词典({pairs}对)"
    except Exception:
        return None, "内置映射表"


def t2s(text, convert):
    return convert(text) if convert else text.translate(T2S_TABLE)


def read_book(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def strip_ws(text):
    return re.sub(r"[ \t\u3000]+", "", text)


def build_layers(lines, convert):
    """返回 [(层名, 拼接串, 行号映射表 list[int]（逐字符对应原始行号）), ...]"""
    layers = []
    # ①逐字：行间保留换行（引文须不含换行即须行内命中）
    joined = "\n".join(lines)
    line_map = []
    for i, ln in enumerate(lines, 1):
        line_map.extend([i] * (len(ln) + 1))
    layers.append(("①逐字", joined, line_map))
    # ②空白归一
    norm_lines = [strip_ws(ln) for ln in lines]
    joined2 = "".join(norm_lines)
    line_map2 = []
    for i, ln in enumerate(norm_lines, 1):
        line_map2.extend([i] * len(ln))
    layers.append(("②空白归一", joined2, line_map2))
    # ③繁简等价（在②基础上）
    simp_lines = [t2s(ln, convert) for ln in norm_lines]
    joined3 = "".join(simp_lines)
    line_map3 = []
    for i, ln in enumerate(simp_lines, 1):
        line_map3.extend([i] * len(ln))
    layers.append(("③繁简等价", joined3, line_map3))
    # ④⑤与③同串（换行在拼接时已去）；⑤差异体现在引文侧正则
    layers.append(("④跨行拼接", joined3, line_map3))
    layers.append(("⑤虚词差异", joined3, line_map3))
    return layers


def quote_for_layer(quote, layer_name, convert):
    q = quote if layer_name.startswith("①") else strip_ws(quote)
    if layer_name.startswith(("③", "④", "⑤")):
        q = t2s(q, convert)
    if layer_name.startswith("⑤"):
        q = "".join(ch + "?" if ch in FUNC_WORDS else ch for ch in q)
    return q


def find_in_layer(text, q, regex):
    if regex:
        try:
            m = re.compile(q).search(text)
        except re.error:
            return -1
        return m.start() if m else -1
    return text.find(q)


def nearest_diff(text, q, convert):
    """最近差异摘要：找最长公共块 + 首个差异点。"""
    sm = difflib.SequenceMatcher(None, q, text, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 2]
    if not blocks:
        return "无≥2字连续命中片段"
    best = max(blocks, key=lambda b: b.size)
    frag = q[best.a:best.a + best.size]
    return f"最长命中片段「{frag}」({best.size}字)，引文长度{len(q)}字"


def main():
    ap = argparse.ArgumentParser(description="古籍引文五层容错验证")
    ap.add_argument("--quote", required=True, help="引文片段")
    ap.add_argument("--book", default=None, help="书名（匹配 data/classics/<书名>.txt；缺省=全库扫）")
    args = ap.parse_args()

    if not os.path.isdir(CLASSICS_DIR):
        print(f"[FAIL] 典籍目录不存在：{CLASSICS_DIR}", file=sys.stderr)
        return 1

    books = []
    if args.book:
        path = os.path.join(CLASSICS_DIR, args.book + ".txt")
        if not os.path.isfile(path):
            # 容错：glob 匹配
            import glob as _g

            hits = _g.glob(os.path.join(CLASSICS_DIR, f"*{args.book}*.txt"))
            if len(hits) != 1:
                print(f"[FAIL] 书名未唯一定位：{args.book}（候选 {[os.path.basename(h) for h in hits]}）",
                      file=sys.stderr)
                return 1
            path = hits[0]
        books.append(path)
    else:
        import glob as _g

        books = sorted(_g.glob(os.path.join(CLASSICS_DIR, "*.txt")))

    convert, conv_name = load_converter()
    print(f"[info] 繁简转换：{conv_name}；扫描 {len(books)} 部", file=sys.stderr)

    for path in books:
        name = os.path.splitext(os.path.basename(path))[0]
        lines = read_book(path).splitlines()
        layers = build_layers(lines, convert)
        for layer_name, text, line_map in layers:
            q = quote_for_layer(args.quote, layer_name, convert)
            regex = layer_name.startswith("⑤")
            pos = find_in_layer(text, q, regex)
            if pos >= 0:
                m = re.search(re.escape(q) if not regex else q, text)
                start = m.start() if m else pos
                # ⑤ 命中起点：regex search 已给 start
                ln_start = line_map[start] if start < len(line_map) else 0
                end = start + (m.end() - m.start() if m else len(q)) - 1
                ln_end = line_map[min(end, len(line_map) - 1)]
                span = f"第{ln_start}行" if ln_start == ln_end else f"第{ln_start}-{ln_end}行"
                print(f"[HIT] {name} {layer_name} {span}")
                print(f"  原文：{text[start:start + 60]}")
                return 0
        # 本书各层差异摘要
        print(f"[miss] {name}")
        for layer_name, text, _ in layers:
            q = quote_for_layer(args.quote, layer_name, convert)
            print(f"  {layer_name}：{nearest_diff(text, q, convert)}", file=sys.stderr)

    print(f"[FAIL] 五层全败，未命中（引文：{args.quote}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
