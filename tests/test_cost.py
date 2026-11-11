"""记账的三件事：价目表按高峰/空闲算对、写日志、汇总。"""

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ME_DB"] = str(Path(tempfile.mkdtemp()) / "cost-test.db")

from app.services import cost  # noqa: E402


class CostTest(unittest.TestCase):
    def test_peak_by_time(self):
        tz = cost.TZ
        self.assertTrue(cost.is_peak(datetime(2026, 11, 10, 10, 0, tzinfo=tz)))  # 周二上午
        self.assertTrue(cost.is_peak(datetime(2026, 11, 10, 15, 0, tzinfo=tz)))  # 周二下午
        self.assertFalse(cost.is_peak(datetime(2026, 11, 10, 13, 0, tzinfo=tz)))  # 午休
        self.assertFalse(cost.is_peak(datetime(2026, 11, 14, 10, 0, tzinfo=tz)))  # 周六

    def test_cost_math(self):
        # 空闲：命中 100 万 × 0.02 + 未命中 100 万 × 1 + 输出 100 万 × 4 = 5.02 元
        usage = {
            "prompt_cache_hit_tokens": 1_000_000,
            "prompt_cache_miss_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
        }
        off = cost.cost_of(usage, now=datetime(2026, 11, 14, 3, 0, tzinfo=cost.TZ))
        self.assertAlmostEqual(off, 5.02, places=6)

    def test_record_and_summary(self):
        tmp = Path(tempfile.mkdtemp()) / "cost.jsonl"
        old = cost.LOG_PATH
        cost.LOG_PATH = tmp
        try:
            cost.record({"prompt_cache_hit_tokens": 2000, "completion_tokens": 500})
            s = cost.summary()
            self.assertEqual(s["calls"], 1)
            self.assertEqual(s["today_calls"], 1)
            self.assertGreater(s["cost"], 0)
        finally:
            cost.LOG_PATH = old


if __name__ == "__main__":
    unittest.main()
