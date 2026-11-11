"""安全备份 data/me.db。

用 SQLite 自带的 backup API，服务正在跑、正在写也能拷，
比直接复制文件安全（直接复制可能拷到写了一半的 WAL 状态）。

用法（项目根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\backup.py
    .\\.venv\\Scripts\\python.exe scripts\\backup.py --to D:\\备份\\分身志
    .\\.venv\\Scripts\\python.exe scripts\\backup.py --list          # 看现有备份
    .\\.venv\\Scripts\\python.exe scripts\\backup.py --keep 30       # 只留最近 30 份
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DB_PATH  # noqa: E402

DEFAULT_KEEP = 14


def default_dir() -> Path:
    return DB_PATH.parent.parent / "backups"


def backups(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("me-*.db"), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 me.db")
    parser.add_argument("--to", help="备份到哪个目录，默认项目下的 backups/")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="只保留最近几份，0 = 不删")
    parser.add_argument("--list", action="store_true", help="列出已有备份后退出")
    args = parser.parse_args()

    out_dir = Path(args.to) if args.to else default_dir()

    if args.list:
        old = backups(out_dir) if out_dir.exists() else []
        if not old:
            print(f"{out_dir} 下还没有备份")
            return 0
        for p in old:
            print(f"{p.name}  {p.stat().st_size / 1024:.0f} KB")
        return 0

    if not DB_PATH.exists():
        print(f"没有数据库：{DB_PATH}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"me-{datetime.now():%Y%m%d-%H%M%S}.db"

    src = sqlite3.connect(DB_PATH)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    print(f"已备份 → {dest}（{dest.stat().st_size / 1024:.0f} KB）")

    if args.keep > 0:
        for p in backups(out_dir)[args.keep:]:
            p.unlink()
            print(f"  已清理旧备份 {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
