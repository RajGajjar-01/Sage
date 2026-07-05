from app.models.agent import Execution
from app.repositories.base import BaseRepository


class ExecutionRepository(BaseRepository):
    async def save(self, execution: Execution) -> Execution:
        cursor = await self._connection.execute(
            """
            INSERT INTO executions (session_id, command, output, exit_code, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                execution.session_id,
                execution.command,
                execution.output,
                execution.exit_code,
                execution.duration_ms,
                execution.created_at,
            ),
        )
        await self._connection.commit()
        execution.id = cursor.lastrowid
        return execution
