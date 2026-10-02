from app.models.agent import now
from app.models.provider import ProviderCredential
from app.repositories.base import BaseRepository


class ProviderRepository(BaseRepository):
    async def upsert(
        self, name: str, api_key: str, model: str, endpoint: str
    ) -> ProviderCredential:
        stamp = now()
        await self._connection.execute(
            """
            INSERT INTO provider_credentials (name, api_key, model, endpoint, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                api_key = excluded.api_key,
                model = excluded.model,
                endpoint = excluded.endpoint,
                updated_at = excluded.updated_at
            """,
            (name, api_key, model, endpoint, stamp, stamp),
        )
        await self._connection.commit()
        credential = await self.get(name)
        assert credential is not None
        return credential

    async def list(self) -> list[ProviderCredential]:
        cursor = await self._connection.execute(
            "SELECT * FROM provider_credentials ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [ProviderCredential.from_row(dict(row)) for row in rows]

    async def get(self, name: str) -> ProviderCredential | None:
        cursor = await self._connection.execute(
            "SELECT * FROM provider_credentials WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        return ProviderCredential.from_row(dict(row)) if row else None
