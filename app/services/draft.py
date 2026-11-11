"""拟稿：对方说了什么 + 我想表达什么 → 两三条候选回复。

只生成草稿，永远不自动发送。
"""

import re

from . import llm, persona

_NUM = re.compile(r"^\s*(?:\d+\s*[.、)．]|[一二两]\s*[、.])\s*")
_QUOTES = "\"'“”‘’「」『』"


def parse_candidates(text: str) -> list[str]:
    """模型偶尔会带编号、引号、开场白，这里做保守清洗。"""
    out: list[str] = []
    for raw in text.splitlines():
        line = _NUM.sub("", raw.strip())
        line = line.strip().strip(_QUOTES).strip()
        if line:
            out.append(line)
    return out[:3]


def draft(theirs: str, intent: str = "") -> list[str]:
    theirs = theirs.strip()
    if not theirs:
        raise ValueError("先贴一下对方说了什么")

    prompt = persona.draft_template().format(
        theirs=theirs,
        intent=intent.strip() or "（没写，看着办）",
    )
    style = persona.style_examples(theirs, limit=3)
    system = persona.system_prompt() + (f"\n\n{style}" if style else "")
    text = llm.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )
    candidates = parse_candidates(text)
    if not candidates:
        raise ValueError("模型没给出可用的草稿，再点一次试试")
    return candidates
