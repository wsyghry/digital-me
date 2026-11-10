"""分身层测试：假模型，不联网、不花钱。

验的是编排逻辑：检索不到不烧 token、命中片段要进提示词、草稿要洗干净。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="digital-me-p2-"))
os.environ.setdefault("ME_DB", str(_TMP / "test.db"))

from app.db import store  # noqa: E402
from app.services import chat, draft, llm, retrieve  # noqa: E402


class P2Base(unittest.TestCase):
    def setUp(self):
        # 每个测试一套独立临时库，跟 test_core 互不影响
        store.DB_PATH = _TMP / f"{self._testMethodName}.db"
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(store.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
        store.init_db()
        store.insert_message("明天上午九点开会，记得带三号柜的图纸")
        store.insert_message("报了周四的体检，早上别吃早饭")


class QuestionSearchTest(P2Base):
    def test_bigrams_skip_pure_function_words(self):
        grams = retrieve.bigrams("明天要带什么？")
        self.assertIn("明天", grams)
        self.assertNotIn("什么", grams)  # 两字都是虚词，丢掉

    def test_question_finds_note(self):
        hits = retrieve.search_for_question("明天要带什么")
        self.assertTrue(hits)
        self.assertIn("三号柜", hits[0]["text"])

    def test_unrelated_question_returns_nothing(self):
        self.assertEqual(retrieve.search_for_question("量子纠缠怎么入门"), [])


class ChatTest(P2Base):
    def test_no_hit_does_not_call_model(self):
        with mock.patch.object(llm, "chat") as fake:
            out = chat.ask("量子纠缠怎么入门")
        fake.assert_not_called()
        self.assertFalse(out["used_llm"])
        self.assertEqual(out["citations"], [])

    def test_hit_sends_only_question_and_snippets(self):
        with mock.patch.object(llm, "chat", return_value="记得带三号柜的图纸 [1]") as fake:
            out = chat.ask("明天要带什么")
        fake.assert_called_once()
        self.assertTrue(out["used_llm"])
        self.assertEqual(len(out["citations"]), 1)

        messages = fake.call_args.args[0]
        user_text = messages[-1]["content"]
        self.assertIn("明天要带什么", user_text)
        self.assertIn("三号柜", user_text)
        self.assertNotIn("体检", user_text)  # 没命中的记录不许进提示词

    def test_unknown_model_error_becomes_llm_error(self):
        with mock.patch.object(llm, "chat", side_effect=llm.LLMError("Key 不对", 502)):
            with self.assertRaises(llm.LLMError):
                chat.ask("明天要带什么")


class DraftTest(P2Base):
    def test_parse_strips_numbering_and_quotes(self):
        text = '1. “行，明天给你”\n2、明天上午发你\n\n以上。'
        self.assertEqual(draft.parse_candidates(text), ["行，明天给你", "明天上午发你", "以上。"])

    def test_empty_theirs_raises(self):
        with self.assertRaises(ValueError):
            draft.draft("   ")

    def test_draft_returns_candidates(self):
        with mock.patch.object(llm, "chat", return_value="1. 收到\n2. 我看看安排"):
            out = draft.draft("明天能给我吗？", "明天给")
        self.assertEqual(out, ["收到", "我看看安排"])

    def test_garbage_output_raises(self):
        with mock.patch.object(llm, "chat", return_value="  \n "):
            with self.assertRaises(ValueError):
                draft.draft("在吗")


if __name__ == "__main__":
    unittest.main()
