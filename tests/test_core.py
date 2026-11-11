"""关键路径测试：写入去重、两路检索、编辑、删除、导出。

跑法：在项目根目录执行
    .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v

测试用临时库，绝不碰 data/me.db。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="digital-me-test-")
os.environ["ME_DB"] = str(Path(_TMP) / "test.db")

from app.db import store  # noqa: E402  必须在设置 ME_DB 之后导入
from app.services import retrieve  # noqa: E402


def wipe():
    conn = store._connect()
    try:
        conn.execute("DELETE FROM messages")
        conn.commit()
    finally:
        conn.close()


class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()

    def setUp(self):
        wipe()

    def test_insert_and_dedup(self):
        first = store.insert_message("明天上午九点开会", ts="2026-11-10T09:00:00+08:00")
        self.assertIsNotNone(first)
        self.assertEqual(first["text"], "明天上午九点开会")
        again = store.insert_message("明天上午九点开会", ts="2026-11-10T09:00:00+08:00")
        self.assertIsNone(again, "同一条应被判重")
        self.assertEqual(store.count_messages(), 1)

    def test_list_keyset(self):
        for i in range(5):
            store.insert_message(f"第 {i} 条", ts=f"2026-11-10T0{i}:00:00+08:00")
        page = store.list_messages(limit=2)
        self.assertEqual([r["text"] for r in page], ["第 4 条", "第 3 条"])
        older = store.list_messages(limit=2, before_id=page[-1]["id"])
        self.assertEqual([r["text"] for r in older], ["第 2 条", "第 1 条"])

    def test_search_three_chars(self):
        store.insert_message("今天上午和产品对了三号柜的排期", ts="2026-11-10T10:00:00+08:00")
        store.insert_message("明天要给老板看初稿", ts="2026-11-10T11:00:00+08:00")
        hits = retrieve.search("三号柜")
        self.assertEqual(len(hits), 1)
        self.assertIn("三号柜", hits[0]["text"])

    def test_search_two_chars(self):
        store.insert_message("明天上午九点开会", ts="2026-11-10T09:00:00+08:00")
        self.assertEqual(len(retrieve.search("上午")), 1, "两字必须走 LIKE 兜底")
        self.assertEqual(len(retrieve.search("九点")), 1)

    def test_search_punctuation(self):
        store.insert_message("报销（7月）的单子放三号柜", ts="2026-11-10T09:00:00+08:00")
        self.assertEqual(len(retrieve.search("报销（7月）")), 1)
        self.assertEqual(len(retrieve.search('"三号柜')), 1, "开头的引号不能把查询弄坏")
        self.assertEqual(len(retrieve.search("三号柜，")), 1)

    def test_search_mixed_long_short(self):
        store.insert_message("明天上午九点开会，带三号柜图纸", ts="2026-11-10T09:00:00+08:00")
        store.insert_message("明天的午饭", ts="2026-11-10T12:00:00+08:00")
        hits = retrieve.search("明天 三号柜")
        self.assertEqual(len(hits), 1)

    def test_update_reindexes(self):
        rec = store.insert_message("旧内容提三号柜", ts="2026-11-10T09:00:00+08:00")
        store.update_message(rec["id"], "新内容提五号柜")
        self.assertEqual(len(retrieve.search("三号柜")), 0, "改完之后旧词不该还搜得到")
        self.assertEqual(len(retrieve.search("五号柜")), 1)

    def test_update_missing(self):
        self.assertIsNone(store.update_message(9999, "不存在"))

    def test_delete(self):
        rec = store.insert_message("删掉我", ts="2026-11-10T09:00:00+08:00")
        self.assertTrue(store.delete_message(rec["id"]))
        self.assertFalse(store.delete_message(rec["id"]))
        self.assertEqual(store.count_messages(), 0)
        self.assertEqual(len(retrieve.search("删掉我")), 0)

    def test_export_markdown(self):
        store.insert_message("导出测试内容", ts="2026-11-10T09:30:00+08:00")
        md = store.export_markdown()
        self.assertIn("## 2026-11-10", md)
        self.assertIn("导出测试内容", md)
        self.assertIn("**09:30**", md)

    def test_export_empty(self):
        self.assertIn("没有记录", store.export_markdown())

    def test_export_filtered_by_person(self):
        store.insert_message(
            "给老王的", ts="2026-11-10T09:00:00+08:00", conv="老王", sender="me"
        )
        store.insert_message(
            "给老李的", ts="2026-11-10T10:00:00+08:00", conv="老李", sender="me"
        )
        md = store.export_markdown(person="老王")
        self.assertIn("给老王的", md)
        self.assertNotIn("给老李的", md)
        self.assertIn("与 老王", md)

    def test_filter_by_day(self):
        store.insert_message("九号的事", ts="2026-11-09T20:00:00+08:00")
        store.insert_message("十号上午的事", ts="2026-11-10T09:00:00+08:00")
        store.insert_message("十号晚上的事", ts="2026-11-10T21:00:00+08:00")

        same_day = store.list_messages(start="2026-11-10", end="2026-11-10")
        self.assertEqual(len(same_day), 2)
        self.assertTrue(all(r["ts"].startswith("2026-11-10") for r in same_day))

        only_ninth = store.list_messages(start="2026-11-09", end="2026-11-09")
        self.assertEqual([r["text"] for r in only_ninth], ["九号的事"])

        ranged = store.list_messages(start="2026-11-09", end="2026-11-10")
        self.assertEqual(len(ranged), 3)

    def test_filter_swaps_reversed_range(self):
        store.insert_message("九号的事", ts="2026-11-09T20:00:00+08:00")
        swapped = store.list_messages(start="2026-11-10", end="2026-11-09")
        self.assertEqual(len(swapped), 1, "start/end 写反了不该返回空")

    def test_filter_search_by_day(self):
        store.insert_message("三号柜的排期", ts="2026-11-09T20:00:00+08:00")
        store.insert_message("三号柜的图纸", ts="2026-11-10T09:00:00+08:00")

        self.assertEqual(len(retrieve.search("三号柜")), 2)
        today = retrieve.search("三号柜", start="2026-11-10", end="2026-11-10")
        self.assertEqual([r["text"] for r in today], ["三号柜的图纸"])

    def test_days_summary(self):
        store.insert_message("九号一", ts="2026-11-09T20:00:00+08:00")
        store.insert_message("十号一", ts="2026-11-10T09:00:00+08:00")
        store.insert_message("十号二", ts="2026-11-10T21:00:00+08:00")

        summary = store.days()
        self.assertEqual(summary[0], {"day": "2026-11-10", "count": 2})
        self.assertEqual(summary[1], {"day": "2026-11-09", "count": 1})


    def test_ext_id_keeps_same_second_twins(self):
        a = store.insert_message("收到", ts="2026-11-11T10:00:00+08:00", ext_id="s4:1")
        b = store.insert_message("收到", ts="2026-11-11T10:00:00+08:00", ext_id="s4:2")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        again = store.insert_message("收到", ts="2026-11-11T10:00:00+08:00", ext_id="s4:1")
        self.assertIsNone(again)
        self.assertEqual(store.count_messages(), 2)

    def test_ext_id_backfills_legacy_row(self):
        store.insert_message("旧行", ts="2026-11-11T11:00:00+08:00")
        dup = store.insert_message(
            "旧行", ts="2026-11-11T11:00:00+08:00", ext_id="s5:9"
        )
        self.assertIsNone(dup)
        conn = store._connect()
        try:
            row = conn.execute("SELECT ext_id FROM messages WHERE text = '旧行'").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["ext_id"], "s5:9")
        self.assertEqual(store.count_messages(), 1)

    def test_filter_by_person(self):
        store.insert_message(
            "A 说的", ts="2026-11-10T09:00:00+08:00", conv="阿A", sender="阿A"
        )
        store.insert_message(
            "B 说的", ts="2026-11-10T10:00:00+08:00", conv="阿B", sender="阿B"
        )
        rows = store.list_messages(limit=10, person="阿A")
        self.assertEqual([r["conv"] for r in rows], ["阿A"])
        rows = retrieve.search("说的", limit=10, person="阿B")
        self.assertEqual([r["conv"] for r in rows], ["阿B"])

    def test_rebuild_persons_skips_groups(self):
        store.insert_message(
            "群里的话", ts="2026-11-10T09:00:00+08:00", conv="某交流群", sender="老王"
        )
        store.insert_message(
            "私聊的话", ts="2026-11-10T10:00:00+08:00", conv="老王", sender="老王"
        )
        store.upsert_conv("某交流群", "wechat", 1)
        store.rebuild_persons()
        names = {p["name"] for p in store.list_persons(100)}
        self.assertIn("老王", names)
        self.assertNotIn("某交流群", names)


    def test_alias_merges_person_and_counts(self):
        store.insert_message("备注名说的", ts="2026-11-10T09:00:00+08:00", conv="老王", sender="老王")
        store.insert_message("昵称说的", ts="2026-11-10T10:00:00+08:00", conv="隔壁老王", sender="隔壁老王")
        store.rebuild_persons()
        store.set_alias("隔壁老王", "老王")
        try:
            rows = store.list_messages(limit=10, person="老王")
            self.assertEqual({r["conv"] for r in rows}, {"老王", "隔壁老王"})
            counts = {p["name"]: p["count"] for p in store.list_persons(100)}
            self.assertNotIn("隔壁老王", counts)
            self.assertEqual(counts["老王"], 2)
        finally:
            store.delete_alias("隔壁老王")

    def test_suggest_aliases_finds_bracket_variants(self):
        store.insert_message("一", ts="2026-11-10T09:00:00+08:00", conv="陈明玥", sender="陈明玥")
        store.insert_message("二", ts="2026-11-10T10:00:00+08:00", conv="陈明玥（工作号）", sender="陈明玥（工作号）")
        store.insert_message("三", ts="2026-11-10T11:00:00+08:00", conv="完全不同的人", sender="完全不同的人")
        store.rebuild_persons()
        rows = store.suggest_aliases(50)
        pairs = {(r["name"], r["person"]) for r in rows}
        self.assertIn(("陈明玥（工作号）", "陈明玥"), pairs)
        self.assertNotIn("完全不同的人", {r["name"] for r in rows} | {r["person"] for r in rows})

    def test_norm_name_ignores_symbols_and_case(self):
        self.assertEqual(store.norm_name("Kevin（工作）"), "kevin")
        self.assertEqual(store.norm_name("k e v i n"), "kevin")
        self.assertEqual(store.norm_name("小 明 🐟"), "小明")

    def test_alias_rejects_cycle(self):
        store.set_alias("甲", "乙")
        try:
            with self.assertRaises(ValueError):
                store.set_alias("乙", "甲")
            with self.assertRaises(ValueError):
                store.set_alias("同一个", "同一个")
        finally:
            store.delete_alias("甲")


    def test_topic_segment_keeps_nearby_messages(self):
        first = store.insert_message(
            "周三行吗", ts="2026-11-10T09:00:00+08:00", conv="老王", sender="老王"
        )
        store.insert_message(
            "行，周三", ts="2026-11-10T09:05:00+08:00", conv="老王", sender="me", is_me=1
        )
        store.insert_message(
            "很久以后", ts="2026-11-10T18:00:00+08:00", conv="老王", sender="老王"
        )
        seg = store.topic_segment(first["id"], minutes=30)
        self.assertEqual([m["text"] for m in seg], ["周三行吗", "行，周三"])


class RetrieveTest(unittest.TestCase):
    def test_build_fts_query_escapes_quotes(self):
        self.assertEqual(retrieve.build_fts_query(["三号柜"]), '"三号柜"')
        self.assertEqual(retrieve.build_fts_query(["a\"b", "c"]), '"a""b" AND "c"')

    def test_split_terms_strips_edge_punctuation(self):
        long_terms, short_terms = retrieve.split_terms("（三号柜） 上午")
        self.assertEqual(long_terms, ["三号柜"])
        self.assertEqual(short_terms, ["上午"])

    def test_split_terms_empty(self):
        self.assertEqual(retrieve.split_terms("   "), ([], []))


if __name__ == "__main__":
    unittest.main()
