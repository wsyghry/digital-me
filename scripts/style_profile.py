"""从你的语料里统计说话风格，生成 data/style-profile.md。

只做统计，不改数据库、不调模型。分身提示词会把这个文件塞进人格层，
让回复先像「你平时的说话方式」，而不是通用 AI 腔。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\style_profile.py
    .\\.venv\\Scripts\\python.exe scripts\\style_profile.py --limit 5000
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\u2190-\u21FF\u2B00-\u2BFF]"
)
STOP = set("的了吗呢吧啊呀哦嗯是在我有你他她它不也就都还很太要会能可以这个那个什么怎么")
PUNCT = "。！？…~～，、；："


def load(limit: int) -> list[str]:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT text FROM messages WHERE is_me = 1 AND kind = 'text' AND text IS NOT NULL"
            " ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for (text,) in rows:
        text = (text or "").replace("\r", " ").replace("\n", " ").strip()
        if 1 <= len(text) <= 300:
            out.append(text)
    return out


def ngrams(texts: list[str], n: int, top: int) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for t in texts:
        clean = re.sub(r"[\s\d\W_]+", "", t)
        for i in range(len(clean) - n + 1):
            gram = clean[i : i + n]
            if any(ch in STOP for ch in gram):
                continue
            if not all("\u4e00" <= ch <= "\u9fff" for ch in gram):
                continue
            counter[gram] += 1
    return [(g, c) for g, c in counter.most_common(top * 3) if c >= 3][:top]


def pct(part: int, whole: int) -> str:
    return f"{part * 100 // max(whole, 1)}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="统计说话风格")
    ap.add_argument("--limit", type=int, default=3000)
    args = ap.parse_args()

    texts = load(args.limit)
    if not texts:
        print("库里没有本人发言，先导入语料")
        return 1

    n = len(texts)
    lens = sorted(len(t) for t in texts)
    median = lens[n // 2]
    short = sum(1 for x in lens if x <= 15)
    long_ = sum(1 for x in lens if x >= 60)
    with_punct_end = sum(1 for t in texts if t[-1] in PUNCT)
    with_period = sum(1 for t in texts if "。" in t)
    with_emoji = sum(1 for t in texts if EMOJI.search(t))
    with_quest = sum(1 for t in texts if "？" in t or "?" in t)
    with_exclaim = sum(1 for t in texts if "！" in t or "!" in t)
    with_ellipsis = sum(1 for t in texts if "…" in t or "..." in t)
    with_tilde = sum(1 for t in texts if "~" in t or "～" in t)

    emoji_counter: Counter[str] = Counter()
    for t in texts:
        emoji_counter.update(EMOJI.findall(t))
    punct_chars: Counter[str] = Counter()
    for t in texts:
        punct_chars.update(ch for ch in t if ch in PUNCT)

    openers = Counter(t[:2] for t in texts if len(t) >= 2)
    closers = Counter(t[-2:] for t in texts if len(t) >= 2)
    grams2 = ngrams(texts, 2, 12)
    grams3 = ngrams(texts, 3, 10)
    addr = Counter()
    for t in texts:
        for word in ("老师", "哥", "姐", "兄弟", "同学", "老板", "师傅"):
            if word in t:
                addr[word] += 1

    lines = []
    lines.append("# 我的说话风格（脚本统计，别手改）")
    lines.append("")
    lines.append(f"> 样本：{n} 条本人发言（最近 {args.limit} 条里取的）· 由 `scripts/style_profile.py` 生成")
    lines.append("")
    lines.append("## 数字")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 句子长度中位数 | {median} 字 |")
    lines.append(f"| 短句（≤15 字）占比 | {pct(short, n)} |")
    lines.append(f"| 长句（≥60 字）占比 | {pct(long_, n)} |")
    lines.append(f"| 结尾带标点 | {pct(with_punct_end, n)} |")
    lines.append(f"| 用过句号 | {pct(with_period, n)} |")
    lines.append(f"| 用过问号 | {pct(with_quest, n)} |")
    lines.append(f"| 用过感叹号 | {pct(with_exclaim, n)} |")
    lines.append(f"| 用过省略号 | {pct(with_ellipsis, n)} |")
    lines.append(f"| 用过波浪号 | {pct(with_tilde, n)} |")
    lines.append(f"| 带 emoji | {pct(with_emoji, n)} |")
    lines.append("")
    if emoji_counter:
        top_emoji = " ".join(f"{e}({c})" for e, c in emoji_counter.most_common(8))
        lines.append(f"**最常用的表情**：{top_emoji}")
        lines.append("")
    if punct_chars:
        top_p = " ".join(f"`{p}`{c}" for p, c in punct_chars.most_common(6))
        lines.append(f"**标点偏好**：{top_p}")
        lines.append("")
    if grams2:
        lines.append("**高频两字**：" + "、".join(g for g, _ in grams2))
        lines.append("")
    if grams3:
        lines.append("**高频三字**：" + "、".join(g for g, _ in grams3))
        lines.append("")
    if addr:
        lines.append("**怎么称呼人**：" + "、".join(f"{w}({c} 次)" for w, c in addr.most_common(4)))
        lines.append("")

    # 给模型看的风格指令（简短、可执行）
    style_bits = []
    style_bits.append(f"句子通常 {median} 字左右，" + ("多短句，很少写长段" if short > n * 0.5 else "长短都有"))
    style_bits.append("结尾" + ("基本不加标点" if with_punct_end < n * 0.4 else "会加标点"))
    if with_period < n * 0.3:
        style_bits.append("很少用句号")
    if with_ellipsis > n * 0.15:
        style_bits.append("爱用省略号")
    if with_tilde > n * 0.1:
        style_bits.append("爱用波浪号")
    if with_emoji > n * 0.15 and emoji_counter:
        style_bits.append("偶尔带表情（常用 " + "".join(e for e, _ in emoji_counter.most_common(3)) + "）")
    else:
        style_bits.append("基本不用表情")
    lines.append("## 给人格层的一句话指令")
    lines.append("")
    lines.append("> " + "；".join(style_bits) + "。")
    lines.append("")
    lines.append("## 最近说过的话（当语气参照）")
    lines.append("")
    for t in texts[:12]:
        shown = t if len(t) <= 60 else t[:59] + "…"
        lines.append(f"- {shown}")
    lines.append("")

    out = config.DB_PATH.parent / "style-profile.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"写出 {out}")
    print("样本", n, "中位长度", median, "短句", pct(short, n), "带句号", pct(with_period, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
