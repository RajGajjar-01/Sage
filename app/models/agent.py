import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

MessageRole = Literal["user", "assistant", "tool_result"]


def now() -> int:
    """Current UTC time as whole seconds -- the timestamp format every table stores."""
    return int(datetime.now(UTC).timestamp())


@dataclass
class Session:
    title: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "active"
    created_at: int = field(default_factory=now)
    updated_at: int = field(default_factory=now)

    @staticmethod
    def from_row(row: dict[str, Any]) -> "Session":
        return Session(
            id=row["id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class Message:
    session_id: str
    role: MessageRole
    content: str
    id: int | None = None
    created_at: int = field(default_factory=now)

    @staticmethod
    def from_row(row: dict[str, Any]) -> "Message":
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )


@dataclass
class Execution:
    session_id: str
    command: str
    output: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    id: int | None = None
    created_at: int = field(default_factory=now)

    @staticmethod
    def from_row(row: dict[str, Any]) -> "Execution":
        return Execution(
            id=row["id"],
            session_id=row["session_id"],
            command=row["command"],
            output=row["output"],
            exit_code=row["exit_code"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )
