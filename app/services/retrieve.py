"""业务层：把用户输入变成检索计划。

两条规则（实测得出，见 docs/data-schema.md）：
1. 长度 ≥ 3 的词能用 FTS5 MATCH，但要包成短语，否则特殊字符会报错；
2. 长度 1~2 的词 trigram 匹配不到，必须用 LIKE 兜底。
"""

from ..db import store


# 用户手打的标点不要喂给 FTS 语法，切词时从两端削掉
_EDGE = "\"'`.,;:!?()[]{}<>-_/\\|…、，。！？：；“”‘’（）《》【】〔〕「」『』"


def split_terms(query: str) -> tuple[list[str], list[str]]:
    """按空白切词，分成「能走 FTS 的长词」与「只能走 LIKE 的短词」。"""
    terms = [t.strip(_EDGE) for t in query.split()]
    terms = [t for t in terms if t]
    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]
    return long_terms, short_terms


def build_fts_query(long_terms: list[str]) -> str:
    """每个词包成短语，词内双引号写两遍转义。"""
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms)


def search(
    query: str,
    limit: int = 50,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    long_terms, short_terms = split_terms(query)
    if not long_terms and not short_terms:
        return []
    return store.search_messages(
        build_fts_query(long_terms), short_terms, limit, start=start, end=end
    )


# ---- 提问专用：整句话搜不到东西，得先退成二元组 ----

_PUNCT = "，。！？、；：,.!?;:\"'“”‘’（）()《》【】〔〕「」『』…—~·-_/\\|"
# 没有区分度的虚字，成对出现时直接丢掉（「什么」「明天」保留，「的吗」丢掉）
_STOP = set("的了着过就都也还和与在有个一不没我是你他她它们啊呀哦吗呢吧这那什么怎样谁哪几啥嘛")


def bigrams(question: str) -> list[str]:
    """把一句人话切成相邻两字，用来做模糊命中。

    中文明明没有空格，整句当短语去 MATCH 一定落空；两字是最小的有信息切片。
    """
    chars = [c for c in question if c not in _PUNCT and not c.isspace()]
    grams: list[str] = []
    for i in range(len(chars) - 1):
        pair = chars[i] + chars[i + 1]
        if pair[0] in _STOP and pair[1] in _STOP:
            continue
        if pair not in grams:
            grams.append(pair)
    return grams


def search_for_question(question: str, limit: int = 8) -> list[dict]:
    """问答用：按命中的二元组个数排序，命中最多的排前面。"""
    grams = bigrams(question)
    if not grams:
        return search(question, limit)

    rows = store.search_any(grams, limit=200)
    scored = []
    for row in rows:
        text = row["text"]
        score = sum(1 for g in grams if g in text)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[1]["ts"] or "", reverse=True)
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:limit]]
