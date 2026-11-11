"""配置：全项目唯一读取环境变量的地方。"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 数据库：默认 data/me.db，可用 ME_DB 或 DATA_DIR 改位置
_db = Path(os.getenv("ME_DB", "data/me.db"))
DB_PATH = (_db if _db.is_absolute() else ROOT / _db).resolve()

WEB_DIR = ROOT / "web"
SCHEMA_PATH = Path(__file__).resolve().parent / "db" / "schema.sql"

HOST = os.getenv("ME_HOST") or os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("ME_PORT") or os.getenv("PORT", "8000"))

# P2 才会用到，缺了不影响记录和搜索
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE = os.getenv("LLM_BASE", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-flash")
PERSONA_NAME = os.getenv("PERSONA_NAME", "我")

# 访问口令：本机留空即可；上公网必须设，否则谁都能读写整库
PASSWORD = os.getenv("ME_PASSWORD", "")


def auth_required() -> bool:
    return bool(PASSWORD)
