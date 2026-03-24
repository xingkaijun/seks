import os
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://seks:change_me@localhost:15432/seks")


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def test_connection() -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return bool(row and row["ok"] == 1)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())


def fetch_books(q: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            b.id,
            b.title,
            b.author,
            b.file_path,
            COALESCE(b.domain_tags, ARRAY[]::text[]) AS domain_tags,
            COUNT(c.id) AS chunk_count
        FROM books b
        LEFT JOIN chunks c ON c.book_id = b.id
    """
    params: list[Any] = []
    if q:
        sql += " WHERE b.title ILIKE %s"
        params.append(f"%{q}%")
    sql += " GROUP BY b.id ORDER BY b.id ASC"
    return fetch_all(sql, tuple(params))


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


def execute_returning(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        return row
