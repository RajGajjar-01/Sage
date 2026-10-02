import aiosqlite

from app.models.agent import now

_DEFAULT_TTL_HOURS = 24


class DocCache:
    """TTL-bounded cache for Tavily search results, keyed by (provider, query)."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def get(self, provider: str, query_key: str) -> str | None:
        key = _normalize(query_key)
        cursor = await self._connection.execute(
            "SELECT response, expires_at FROM doc_cache WHERE provider = ? AND query_key = ?",
            (provider, key),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        response, expires_at = row["response"], row["expires_at"]
        if expires_at < now():
            await self._connection.execute(
                "DELETE FROM doc_cache WHERE provider = ? AND query_key = ?",
                (provider, key),
            )
            await self._connection.commit()
            return None
        return str(response)

    async def set(
        self,
        provider: str,
        query_key: str,
        response: str,
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ) -> None:
        stamp = now()
        key = _normalize(query_key)
        await self._connection.execute(
            """
            INSERT INTO doc_cache (provider, query_key, response, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, query_key) DO UPDATE SET
                response = excluded.response,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (provider, key, response, stamp, stamp + ttl_hours * 3600),
        )
        await self._connection.commit()


def _normalize(key: str) -> str:
    return key.lower().strip()
