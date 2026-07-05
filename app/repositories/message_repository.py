from app.models.agent import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository):
    async def save(self, message: Message) -> Message:
        cursor = await self._connection.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (message.session_id, message.role, message.content, message.created_at),
        )
        await self._connection.commit()
        message.id = cursor.lastrowid
        return message

    async def list_by_session(self, session_id: str) -> list[Message]:
        cursor = await self._connection.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )
        rows = await cursor.fetchall()
        return [Message.from_row(dict(row)) for row in rows]
