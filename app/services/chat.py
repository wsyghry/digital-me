"""问答编排：先检索我的记录，再让模型只基于这几条回答。"""

from . import llm, persona, retrieve

MAX_HITS = 8
NO_HIT = "我没记过这件事。要不要先在「记录」里补一句？"


def _context(hits: list[dict]) -> str:
    lines = []
    for i, m in enumerate(hits, 1):
        stamp = (m["ts"] or "").replace("T", " ")[:16]
        lines.append(f"[{i}] {stamp} {m['text']}")
    return "\n".join(lines)


def ask(question: str, limit: int = MAX_HITS) -> dict:
    """返回 answer / citations / used_llm。检索不到就不烧模型。"""
    question = question.strip()
    hits = retrieve.search_for_question(question, limit)
    if not hits:
        return {"answer": NO_HIT, "citations": [], "used_llm": False}

    prompt = persona.ask_template().format(context=_context(hits), question=question)
    answer = llm.chat(
        [
            {"role": "system", "content": persona.system_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    citations = [{"id": m["id"], "ts": m["ts"], "text": m["text"]} for m in hits]
    return {"answer": answer, "citations": citations, "used_llm": True}
