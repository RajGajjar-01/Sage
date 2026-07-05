import pytest

from app.core.sandbox import Sandbox, SandboxViolationError
from app.services.shell_executor import ShellExecutor


@pytest.fixture
def executor(tmp_path):
    return ShellExecutor(Sandbox(tmp_path / "workspace"), timeout_seconds=5)


@pytest.mark.asyncio
async def test_run_captures_stdout(executor):
    result = await executor.run("echo hello")
    assert result.output == "hello"
    assert result.exit_code == 0
    assert not result.timed_out


@pytest.mark.asyncio
async def test_run_reports_nonzero_exit_code(executor):
    result = await executor.run("exit 3")
    assert result.exit_code == 3


@pytest.mark.asyncio
async def test_run_times_out_long_command(tmp_path):
    executor = ShellExecutor(Sandbox(tmp_path / "workspace"), timeout_seconds=1)
    result = await executor.run("sleep 5")
    assert result.timed_out
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_run_rejects_command_outside_workspace(executor):
    with pytest.raises(SandboxViolationError):
        await executor.run("cat /etc/passwd")


@pytest.mark.asyncio
async def test_run_uses_workspace_as_cwd(executor):
    result = await executor.run("pwd")
    assert result.output == str(executor.working_directory)
