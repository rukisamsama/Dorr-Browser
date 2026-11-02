import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_PATH


def get_connection():
    Path(DATABASE_PATH).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=15,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")

    return connection


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def initialize_database():
    """
    既存の pages テーブルを保持したまま、
    Dorr Search の追加テーブルを作成する。
    """

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                content TEXT DEFAULT '',
                indexed_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                searched_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                url TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_pages_title
            ON pages(title)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_pages_indexed_at
            ON pages(indexed_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_searched_at
            ON search_history(searched_at)
        """)

        # Web版・EXE版で共有する設定。旧キー default_engine は
        # 既存データとの互換性のため残す。
        defaults = {
            "default_engine": "dorr",
            "search_engine": "dorr",
            "homepage": "http://127.0.0.1:8000/",
            "language": "ja",
            "theme": "dark",
            "safe_search": "true",
            "animations": "true",
            "tracker_protection": "false",
        }

        for key, value in defaults.items():
            connection.execute("""
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
            """, (key, value))


def save_page(url, title="", description="", content=""):
    """
    URLが既に存在する場合は内容を更新する。
    """

    with get_connection() as connection:
        connection.execute("""
            INSERT INTO pages (
                url,
                title,
                description,
                content,
                indexed_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                content = excluded.content,
                indexed_at = excluded.indexed_at
        """, (
            url,
            title[:500],
            description[:1000],
            content,
            now_iso(),
        ))


def get_page_count():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM pages"
        ).fetchone()

        return row["count"] if row else 0


def get_settings():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT key, value FROM settings"
        ).fetchall()

    return {
        row["key"]: row["value"]
        for row in rows
    }


def update_settings(values):
    if not isinstance(values, dict):
        raise ValueError("設定データが不正です。")

    with get_connection() as connection:
        for key, value in values.items():
            if not isinstance(key, str):
                continue

            if len(key) > 100:
                continue

            if isinstance(value, (dict, list)):
                continue

            connection.execute("""
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value
            """, (key, str(value)))


def add_history(query):
    query = str(query).strip()

    if not query:
        return

    with get_connection() as connection:
        connection.execute("""
            INSERT INTO search_history (query, searched_at)
            VALUES (?, ?)
        """, (query[:500], now_iso()))

        # 履歴が増えすぎないよう、古いものを整理
        connection.execute("""
            DELETE FROM search_history
            WHERE id NOT IN (
                SELECT id
                FROM search_history
                ORDER BY id DESC
                LIMIT 500
            )
        """)


def get_history(limit=30):
    limit = max(1, min(int(limit), 100))

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, query, searched_at
            FROM search_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]


def clear_history():
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM search_history"
        )


def add_bookmark(title, url):
    title = str(title).strip()[:500]
    url = str(url).strip()

    if not url.startswith(("http://", "https://")):
        raise ValueError("HTTPまたはHTTPSのURLを指定してください。")

    with get_connection() as connection:
        connection.execute("""
            INSERT INTO bookmarks (title, url, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title
        """, (title, url, now_iso()))


def get_bookmarks():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, title, url, created_at
            FROM bookmarks
            ORDER BY id DESC
        """).fetchall()

    return [dict(row) for row in rows]


def delete_bookmark(bookmark_id):
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM bookmarks WHERE id = ?",
            (int(bookmark_id),),
        )