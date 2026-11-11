"""人格层：把 prompts/persona.md 和我的真实语气样本拼成系统提示词。

只读数据库，不写、不改。
"""

from pathlib import Path

from .. import config
from ..db import store

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _read(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _sample_block() -> str:
    """按场景分组的语气样本：短回复 / 日常 / 长一点。

    固定取最近的几条（不随机），提示词前缀才稳定，能命中 DeepSeek 的缓存价。
    """
    scenes = store.sample_by_scene()
    lines: list[str] = []
    for label, key in (("短回复", "short"), ("日常对话", "mid"), ("说长一点的时候", "long")):
        items = scenes.get(key) or []
        if not items:
            continue
        lines.append(f"{label}：")
        lines += [f"- {s}" for s in items]
    if not lines:
        return "- （还没有语料，先按短句、口语、少客套来说）"
    return "\n".join(lines)


def _style_block() -> str:
    """读 scripts/style_profile.py 统计出来的风格画像，取「一句话指令」和几句原话。"""
    path = config.DB_PATH.parent / "style-profile.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    hint = ""
    recent: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("> ") and "字左右" in line:
            hint = line[2:].strip()
        if line.startswith("- ") and "最近说过的话" in "\n".join(lines[max(0, i - 20):i]):
            recent.append(line[2:].strip())
    parts: list[str] = []
    if hint:
        parts.append(f"你平时说话的特点：{hint}")
    if recent:
        parts.append("你最近的原话（学这个语气，不要照抄内容）：")
        parts += [f"- {s}" for s in recent[:6]]
    return "\n".join(parts)


def style_examples(question: str, limit: int = 3) -> str:
    """跟这个问题语境相近的、我说过的话，做 few-shot 语气参照。"""
    from .retrieve import bigrams

    terms = bigrams(question)[:6]
    if not terms:
        return ""
    try:
        items = store.my_style_examples(terms, limit=limit)
    except Exception:
        return ""
    if not items:
        return ""
    return "我过去在类似语境里是这么说的（只学语气，别复述）：\n" + "\n".join(f"- {s}" for s in items)


def system_prompt() -> str:
    """人格 + 语气样本 + 风格画像。"""
    base = _read("persona.md").format(name=config.PERSONA_NAME, samples=_sample_block())
    style = _style_block()
    return f"{base}\n\n## 你的说话习惯（从你的真实语料统计出来的）\n{style}" if style else base


def ask_template() -> str:
    return _read("ask.md")


def draft_template() -> str:
    return _read("draft.md")
