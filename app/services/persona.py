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


def system_prompt() -> str:
    """人格 + 语气样本。"""
    return _read("persona.md").format(name=config.PERSONA_NAME, samples=_sample_block())


def ask_template() -> str:
    return _read("ask.md")


def draft_template() -> str:
    return _read("draft.md")
