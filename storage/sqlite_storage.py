import sqlite3
import json
import logging
from typing import Optional
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)


class SQLiteStorage:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS news (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash  TEXT UNIQUE,
                    title         TEXT NOT NULL,
                    url           TEXT NOT NULL,
                    source        TEXT,
                    source_type   TEXT,
                    published_at  TEXT,
                    snippet       TEXT,
                    full_text     TEXT,
                    ai_summary    TEXT,
                    ai_relevance  REAL,
                    ai_topics     TEXT,
                    ai_key_facts  TEXT,
                    created_at    TEXT DEFAULT (datetime('now')),
                    notified      INTEGER DEFAULT 0,
                    filter_status TEXT DEFAULT 'saved'
                );
                CREATE INDEX IF NOT EXISTS idx_news_hash     ON news(content_hash);
                CREATE INDEX IF NOT EXISTS idx_news_date     ON news(created_at);
                CREATE INDEX IF NOT EXISTS idx_news_notified ON news(notified);
                CREATE INDEX IF NOT EXISTS idx_news_source   ON news(source_type);
            """)
            # migration: add filter_status if DB already exists without it
            try:
                conn.execute("ALTER TABLE news ADD COLUMN filter_status TEXT DEFAULT 'saved'")
            except Exception:
                pass
        logger.debug("DB initialized at %s", self.db_path)

    def exists(self, content_hash: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM news WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return row is not None

    def url_exists(self, url: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM news WHERE url = ?", (url,)
            ).fetchone()
            return row is not None

    def save(self, item: NewsItem, filter_status: str = "saved") -> Optional[int]:
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO news
                       (content_hash, title, url, source, source_type,
                        published_at, snippet, full_text,
                        ai_summary, ai_relevance,
                        ai_topics, ai_key_facts, filter_status)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item.content_hash,
                        item.title,
                        item.url,
                        item.source,
                        item.source_type,
                        item.published_at,
                        item.snippet,
                        item.full_text,
                        item.ai_summary,
                        item.ai_relevance,
                        json.dumps(item.ai_topics or [], ensure_ascii=False),
                        json.dumps(item.ai_key_facts or [], ensure_ascii=False),
                        filter_status,
                    ),
                )
                if cursor.lastrowid:
                    logger.info("Saved [%s]: %s", filter_status, item.title[:80])
                    return cursor.lastrowid
                else:
                    logger.debug("Duplicate skipped: %s", item.title[:80])
                    return None
        except Exception as e:
            logger.error("Save error for %r: %s", item.title, e)
            return None

    def get_latest(self, limit: int = 200, include_rejected: bool = False) -> list[dict]:
        with self._get_conn() as conn:
            where = "" if include_rejected else "WHERE filter_status IN ('saved') OR filter_status IS NULL"
            rows = conn.execute(
                f"SELECT * FROM news {where} ORDER BY COALESCE(published_at, created_at) DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_unnotified(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM news WHERE notified = 0 ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_notified(self, news_id: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE news SET notified = 1 WHERE id = ?", (news_id,))

    def stats(self) -> dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
            by_source = dict(conn.execute(
                "SELECT source, COUNT(*) FROM news GROUP BY source"
            ).fetchall())
            return {"total": total, "by_source": by_source}
