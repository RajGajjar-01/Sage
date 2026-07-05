import pytest

from app.core.database import create_connection


@pytest.mark.asyncio
async def test_create_connection_succeeds_in_writable_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.core.database.settings.DB_PATH", str(tmp_path / "agent.db")
    )

    connection = await create_connection()
    await connection.close()


@pytest.mark.asyncio
async def test_create_connection_raises_clear_error_for_readonly_directory(
    tmp_path, monkeypatch
):
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o500)
    monkeypatch.setattr(
        "app.core.database.settings.DB_PATH", str(readonly_dir / "agent.db")
    )

    try:
        with pytest.raises(PermissionError, match="Cannot write to"):
            await create_connection()
    finally:
        readonly_dir.chmod(0o700)


@pytest.mark.asyncio
async def test_create_connection_raises_clear_error_for_readonly_existing_file(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "agent.db"
    db_path.write_text("")
    db_path.chmod(0o400)
    monkeypatch.setattr("app.core.database.settings.DB_PATH", str(db_path))

    try:
        with pytest.raises(PermissionError, match="Cannot write to"):
            await create_connection()
    finally:
        db_path.chmod(0o600)
