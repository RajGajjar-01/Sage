from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite
from fastapi import Request

from app.core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT    PRIMARY KEY,
    title      TEXT    NOT NULL DEFAULT 'New session',
    status     TEXT    NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL REFERENCES sessions(id),
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL REFERENCES sessions(id),
    command     TEXT    NOT NULL,
    output      TEXT    NOT NULL DEFAULT '',
    exit_code   INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_cache (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    provider   TEXT    NOT NULL,
    query_key  TEXT    NOT NULL,
    response   TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    UNIQUE(provider, query_key)
);
CREATE TABLE IF NOT EXISTS provider_credentials (
    name       TEXT    PRIMARY KEY,
    api_key    TEXT    NOT NULL,
    model      TEXT    NOT NULL,
    endpoint   TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_executions_session ON executions(session_id);
CREATE INDEX IF NOT EXISTS idx_doc_cache_lookup ON doc_cache(provider, query_key);
"""


async def create_connection() -> aiosqlite.Connection:
    """Open the shared SQLite connection and make sure the schema exists."""
    db_path = Path(settings.DB_PATH).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = await aiosqlite.connect(db_path)
    connection.row_factory = aiosqlite.Row
    await connection.executescript(_SCHEMA)
    await connection.commit()
    return connection


async def get_db(request: Request) -> AsyncGenerator[aiosqlite.Connection]:
    yield request.app.state.db
