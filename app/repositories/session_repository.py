from app.models.agent import Session, now
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository):
    async def create(self, title: str) -> Session:
        session = Session(title=title)
        await self._connection.execute(
            "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                session.id,
                session.title,
                session.status,
                session.created_at,
                session.updated_at,
            ),
        )
        await self._connection.commit()
        return session

    async def list(self, limit: int = 20) -> list[Session]:
        cursor = await self._connection.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [Session.from_row(dict(row)) for row in rows]

    async def get(self, session_id: str) -> Session | None:
        cursor = await self._connection.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return Session.from_row(dict(row)) if row else None

    async def touch(self, session_id: str) -> None:
        await self._connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now(), session_id)
        )
        await self._connection.commit()

    async def update_status(self, session_id: str, status: str) -> None:
        await self._connection.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now(), session_id),
        )
        await self._connection.commit()
