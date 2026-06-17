"""Database-laag: SQLite (default) of PostgreSQL (optioneel via DATABASE_URL).

Tabellen: searches, posts, comments, analysis_results, exports.

De API is bewust klein gehouden: ``init_db``, ``save_search``, ``save_posts``,
``save_comments``, ``save_analysis``, ``save_export`` en wat lees-helpers. Voor
beide backends gebruiken we parameter-placeholders die per dialect verschillen
(``?`` voor SQLite, ``%s`` voor Postgres).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from .config import Config
from .parser import Comment, Post
from .utils import get_logger, now_iso

logger = get_logger()


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keywords TEXT,
        subreddits TEXT,
        sort TEXT,
        time_filter TEXT,
        num_posts INTEGER DEFAULT 0,
        num_comments INTEGER DEFAULT 0,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS posts (
        post_id TEXT,
        search_id INTEGER,
        subreddit TEXT,
        title TEXT,
        selftext TEXT,
        url TEXT,
        score INTEGER,
        num_comments INTEGER,
        created_date TEXT,
        permalink TEXT,
        keyword TEXT,
        flair TEXT,
        source_url TEXT,
        collected_at TEXT,
        dedup_key TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        comment_id TEXT,
        post_id TEXT,
        parent_id TEXT,
        search_id INTEGER,
        body TEXT,
        score INTEGER,
        created_date TEXT,
        depth INTEGER,
        permalink TEXT,
        keyword TEXT,
        subreddit TEXT,
        source_url TEXT,
        collected_at TEXT,
        dedup_key TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_id INTEGER,
        kind TEXT,
        payload TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_id INTEGER,
        filename TEXT,
        format TEXT,
        path TEXT,
        created_at TEXT
    )
    """,
]

# Postgres-variant van AUTOINCREMENT-PK.
_PG_SCHEMA_FIXUPS = [
    ("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"),
]


class Database:
    """Dunne wrapper rond SQLite/Postgres met dialect-bewuste placeholders."""

    def __init__(self, config: Config):
        self.config = config
        self.is_postgres = config.uses_postgres
        self.placeholder = "%s" if self.is_postgres else "?"
        self._conn = None

    # ------------------------------------------------------------- connection
    def connect(self):
        if self._conn is not None:
            return self._conn
        if self.is_postgres:
            try:
                import psycopg2  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "psycopg2-binary is vereist voor PostgreSQL. "
                    "Installeer met: pip install psycopg2-binary"
                ) from exc
            self._conn = psycopg2.connect(self.config.database_url)
        else:
            self.config.data_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.config.sqlite_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def cursor(self):
        conn = self.connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ schema
    def init_db(self) -> None:
        with self.cursor() as cur:
            for stmt in SCHEMA_STATEMENTS:
                if self.is_postgres:
                    for old, new in _PG_SCHEMA_FIXUPS:
                        stmt = stmt.replace(old, new)
                cur.execute(stmt)
        logger.info(
            "Database geïnitialiseerd (%s).",
            "PostgreSQL" if self.is_postgres else f"SQLite @ {self.config.sqlite_path}",
        )

    # ------------------------------------------------------------------- write
    def save_search(
        self,
        keywords: Iterable[str],
        subreddits: Iterable[str],
        sort: str,
        time_filter: str,
        num_posts: int = 0,
        num_comments: int = 0,
    ) -> int:
        ph = self.placeholder
        sql = (
            f"INSERT INTO searches "
            f"(keywords, subreddits, sort, time_filter, num_posts, num_comments, created_at) "
            f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"
        )
        params = (
            ", ".join(keywords),
            ", ".join(subreddits),
            sort,
            time_filter,
            num_posts,
            num_comments,
            now_iso(),
        )
        with self.cursor() as cur:
            if self.is_postgres:
                cur.execute(sql + " RETURNING id", params)
                return int(cur.fetchone()[0])
            cur.execute(sql, params)
            return int(cur.lastrowid)

    def save_posts(self, posts: List[Post], search_id: Optional[int] = None) -> int:
        if not posts:
            return 0
        ph = self.placeholder
        conflict = "" if self.is_postgres else "OR IGNORE "
        sql = (
            f"INSERT {conflict}INTO posts "
            f"(post_id, search_id, subreddit, title, selftext, url, score, num_comments, "
            f"created_date, permalink, keyword, flair, source_url, collected_at, dedup_key) "
            f"VALUES ({', '.join([ph] * 15)})"
        )
        if self.is_postgres:
            sql += " ON CONFLICT (dedup_key) DO NOTHING"
        rows = [
            (
                p.post_id, search_id, p.subreddit, p.title, p.selftext, p.url,
                p.score, p.num_comments, p.created_date, p.permalink, p.keyword,
                p.flair, p.source_url, p.collected_at, p.dedup_key,
            )
            for p in posts
        ]
        with self.cursor() as cur:
            cur.executemany(sql, rows)
        return len(rows)

    def save_comments(self, comments: List[Comment], search_id: Optional[int] = None) -> int:
        if not comments:
            return 0
        ph = self.placeholder
        conflict = "" if self.is_postgres else "OR IGNORE "
        sql = (
            f"INSERT {conflict}INTO comments "
            f"(comment_id, post_id, parent_id, search_id, body, score, created_date, "
            f"depth, permalink, keyword, subreddit, source_url, collected_at, dedup_key) "
            f"VALUES ({', '.join([ph] * 14)})"
        )
        if self.is_postgres:
            sql += " ON CONFLICT (dedup_key) DO NOTHING"
        rows = [
            (
                c.comment_id, c.post_id, c.parent_id, search_id, c.body, c.score,
                c.created_date, c.depth, c.permalink, c.keyword, c.subreddit,
                c.source_url, c.collected_at, c.dedup_key,
            )
            for c in comments
        ]
        with self.cursor() as cur:
            cur.executemany(sql, rows)
        return len(rows)

    def save_analysis(self, search_id: Optional[int], kind: str, payload: Dict[str, Any]) -> int:
        ph = self.placeholder
        sql = (
            f"INSERT INTO analysis_results (search_id, kind, payload, created_at) "
            f"VALUES ({ph}, {ph}, {ph}, {ph})"
        )
        params = (search_id, kind, json.dumps(payload, ensure_ascii=False), now_iso())
        with self.cursor() as cur:
            if self.is_postgres:
                cur.execute(sql + " RETURNING id", params)
                return int(cur.fetchone()[0])
            cur.execute(sql, params)
            return int(cur.lastrowid)

    def save_export(
        self, search_id: Optional[int], filename: str, fmt: str, path: str
    ) -> int:
        ph = self.placeholder
        sql = (
            f"INSERT INTO exports (search_id, filename, format, path, created_at) "
            f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})"
        )
        params = (search_id, filename, fmt, path, now_iso())
        with self.cursor() as cur:
            if self.is_postgres:
                cur.execute(sql + " RETURNING id", params)
                return int(cur.fetchone()[0])
            cur.execute(sql, params)
            return int(cur.lastrowid)

    # -------------------------------------------------------------------- read
    def latest_search_id(self) -> Optional[int]:
        """Id van de meest recente zoekopdracht, of None."""
        with self.cursor() as cur:
            cur.execute("SELECT id FROM searches ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            return int(row[0]) if row else None

    def fetch_posts(self, search_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._fetch("posts", search_id)

    def fetch_comments(self, search_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._fetch("comments", search_id)

    def _fetch(self, table: str, search_id: Optional[int]) -> List[Dict[str, Any]]:
        ph = self.placeholder
        with self.cursor() as cur:
            if search_id is not None:
                cur.execute(f"SELECT * FROM {table} WHERE search_id = {ph}", (search_id,))
            else:
                cur.execute(f"SELECT * FROM {table}")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
