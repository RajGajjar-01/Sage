from dataclasses import dataclass, field
from typing import Any

from app.models.agent import now


@dataclass
class ProviderCredential:
    name: str
    api_key: str
    model: str
    endpoint: str
    created_at: int = field(default_factory=now)
    updated_at: int = field(default_factory=now)

    @staticmethod
    def from_row(row: dict[str, Any]) -> "ProviderCredential":
        return ProviderCredential(
            name=row["name"],
            api_key=row["api_key"],
            model=row["model"],
            endpoint=row["endpoint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
