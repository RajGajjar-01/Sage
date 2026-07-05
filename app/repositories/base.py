import aiosqlite


class BaseRepository:
    """Shared SQLite connection handle for repository subclasses."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
