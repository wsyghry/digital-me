"""人格层：把 prompts/persona.md 和我的真实语气样本拼成系统提示词。

只读数据库，不写、不改。
"""

from pathlib import Path

from .. import config
from ..db import store

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _read(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def system_prompt() -> str:
    """人格 + 语气样本。样本固定取最近的，保证前缀稳定、能吃到缓存价。"""
    samples = store.sample_my_messages(10)
    block = "\n".join(f"- {s}" for s in samples)
    if not block:
        block = "- （还没有语料，先按短句、口语、少客套来说）"
    return _read("persona.md").format(name=config.PERSONA_NAME, samples=block)


def ask_template() -> str:
    return _read("ask.md")


def draft_template() -> str:
    return _read("draft.md")
