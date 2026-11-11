"""问答编排：先检索我的记录，再让模型只基于这几条回答。"""

from ..db import store
from . import llm, persona, retrieve

MAX_HITS = 8
SEGMENT_HITS = 3  # 前几条命中补上「话题段」上下文，后面的只给单条
SEGMENT_MINUTES = 30
NO_HIT = "我没记过这件事。要不要先在「记录」里补一句？"


def _speaker(m: dict) -> str:
    if m.get("is_me"):
        return "我"
    conv = m.get("conv")
    if conv and conv != "自己":
        return conv
    return m.get("sender") or "对方"


def _one_line(text: str, limit: int = 200) -> str:
    return text.replace("\r", " ").replace("\n", " ").strip()[:limit]


def _context(hits: list[dict]) -> str:
    """先给命中那条，再给同会话前后文——很多短句离开上下文就答不准。"""
    lines: list[str] = []
    for i, m in enumerate(hits[:SEGMENT_HITS], 1):
        stamp = (m["ts"] or "").replace("T", " ")[:16]
        lines.append(f"[{i}] {stamp} 命中：{_one_line(m['text'])}")
        conv = m.get("conv")
        if conv and conv != "自己":
            seg = store.topic_segment(m["id"], SEGMENT_MINUTES)
            if len(seg) > 1:
                lines.append("  前后文：")
                for s in seg:
                    lines.append(f"    {_speaker(s)}：{_one_line(s['text'], 120)}")
    for i, m in enumerate(hits[SEGMENT_HITS:], SEGMENT_HITS + 1):
        stamp = (m["ts"] or "").replace("T", " ")[:16]
        lines.append(f"[{i}] {stamp} {_one_line(m['text'])}")
    return "\n".join(lines)


def ask(question: str, limit: int = MAX_HITS) -> dict:
    """返回 answer / citations / used_llm。检索不到就不烧模型。"""
    question = question.strip()
    hits = retrieve.search_for_question(question, limit)
    if not hits:
        return {"answer": NO_HIT, "citations": [], "used_llm": False}

    prompt = persona.ask_template().format(context=_context(hits), question=question)
    style = persona.style_examples(question)
    system = persona.system_prompt() + (f"\n\n{style}" if style else "")
    answer = llm.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    citations = [{"id": m["id"], "ts": m["ts"], "text": m["text"]} for m in hits]
    return {"answer": answer, "citations": citations, "used_llm": True}
