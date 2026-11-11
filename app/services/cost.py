"""调用花费记账。

DeepSeek 每次返回都带 usage，把它落到 data/llm-cost.jsonl，一行一次调用。
单价按官方价目表（元 / 百万 tokens），高峰时段用高峰价：
  deepseek-flash  缓存命中 0.02 / 0.04，未命中 1 / 2，输出 4 / 8（空闲 / 高峰）
高峰 = 工作日 9:00-12:00 与 14:00-18:00（东八区）。
"""

import json
from datetime import datetime, timedelta, timezone

from app.config import DB_PATH, LLM_MODEL

LOG_PATH = DB_PATH.parent / "llm-cost.jsonl"
TZ = timezone(timedelta(hours=8))

# 元 / 百万 tokens：(空闲命中, 空闲未命中, 空闲输出, 高峰命中, 高峰未命中, 高峰输出)
PRICES = {
    "deepseek-flash": (0.02, 1.0, 4.0, 0.04, 2.0, 8.0),
}
DEFAULT_PRICES = PRICES["deepseek-flash"]


def is_peak(now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    if now.weekday() > 4:
        return False
    return 9 <= now.hour < 12 or 14 <= now.hour < 18


def price(model: str, now: datetime | None = None) -> tuple[float, float, float]:
    hit, miss, out, phit, pmiss, pout = PRICES.get(model, DEFAULT_PRICES)
    return (phit, pmiss, pout) if is_peak(now) else (hit, miss, out)


def cost_of(usage: dict, model: str = LLM_MODEL, now: datetime | None = None) -> float:
    hit = usage.get("prompt_cache_hit_tokens") or 0
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:  # 兼容没有缓存字段的返回
        miss = max((usage.get("prompt_tokens") or 0) - hit, 0)
    out = usage.get("completion_tokens") or 0
    hit_price, miss_price, out_price = price(model, now)
    return (hit * hit_price + miss * miss_price + out * out_price) / 1_000_000


def record(usage: dict, model: str = LLM_MODEL) -> float:
    """写一行账，返回这次花费（元）。日志坏了也不该影响回答。"""
    spend = cost_of(usage, model)
    line = {
        "at": datetime.now(TZ).isoformat(timespec="seconds"),
        "model": model,
        "peak": is_peak(),
        "hit": usage.get("prompt_cache_hit_tokens") or 0,
        "miss": usage.get("prompt_cache_miss_tokens")
        if usage.get("prompt_cache_miss_tokens") is not None
        else max((usage.get("prompt_tokens") or 0) - (usage.get("prompt_cache_hit_tokens") or 0), 0),
        "out": usage.get("completion_tokens") or 0,
        "cost": round(spend, 8),
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return spend


def _rows() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = []
    for raw in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return rows


def summary() -> dict:
    rows = _rows()
    today = datetime.now(TZ).date().isoformat()
    today_cost = sum(r.get("cost", 0) for r in rows if str(r.get("at", "")).startswith(today))
    return {
        "calls": len(rows),
        "cost": round(sum(r.get("cost", 0) for r in rows), 6),
        "today_cost": round(today_cost, 6),
        "today_calls": sum(1 for r in rows if str(r.get("at", "")).startswith(today)),
        "peak_now": is_peak(),
        "model": LLM_MODEL,
    }
