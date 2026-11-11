"""访问口令：只在设置 ME_PASSWORD 时生效，且不能误伤登录页与健康检查。"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="me-test-auth-")
os.environ["ME_DB"] = str(Path(_tmp) / "me.db")

from starlette.requests import Request  # noqa: E402

from app import auth, config  # noqa: E402


def make_request(path: str, cookie: str = "") -> Request:
    headers = [(b"cookie", f"me_auth={cookie}".encode())] if cookie else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1),
        }
    )


class AuthTest(unittest.TestCase):
    def setUp(self):
        self._old = config.PASSWORD

    def tearDown(self):
        config.PASSWORD = self._old

    def test_no_password_allows_everything(self):
        config.PASSWORD = ""
        self.assertFalse(auth.enabled())
        self.assertIsNone(auth.check(make_request("/api/messages")))

    def test_api_blocked_without_cookie(self):
        config.PASSWORD = "s3cret"
        resp = auth.check(make_request("/api/messages"))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("口令", json.loads(resp.body)["detail"])

    def test_health_and_login_stay_public(self):
        config.PASSWORD = "s3cret"
        self.assertIsNone(auth.check(make_request("/api/health")))
        self.assertIsNone(auth.check(make_request("/login")))
        self.assertIsNone(auth.check(make_request("/api/login")))

    def test_page_redirects_to_login(self):
        config.PASSWORD = "s3cret"
        resp = auth.check(make_request("/"))
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["location"], "/login")

    def test_correct_cookie_passes(self):
        config.PASSWORD = "s3cret"
        self.assertIsNone(auth.check(make_request("/api/messages", cookie=auth._token())))
        self.assertIsNotNone(auth.check(make_request("/api/messages", cookie="wrong")))

    def test_password_change_invalidates_cookie(self):
        config.PASSWORD = "s3cret"
        token = auth._token()
        config.PASSWORD = "another"
        self.assertIsNotNone(auth.check(make_request("/api/messages", cookie=token)))

    def test_login_endpoint(self):
        config.PASSWORD = "s3cret"

        def call(password: str):
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/login",
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"",
            }
            req = Request(scope)

            async def body():
                return json.dumps({"password": password}).encode()

            req.body = body
            return asyncio.run(auth.login(req))

        bad = call("nope")
        self.assertEqual(bad.status_code, 401)

        good = call("s3cret")
        self.assertEqual(good.status_code, 200)
        self.assertIn("me_auth=", good.headers["set-cookie"])
        self.assertIn("HttpOnly", good.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
