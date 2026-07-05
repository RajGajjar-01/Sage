import pytest

from app.core.sandbox import Sandbox, SandboxViolationError


@pytest.fixture
def sandbox(tmp_path):
    return Sandbox(tmp_path / "workspace")


def test_resolve_relative_path_within_workspace(sandbox):
    resolved = sandbox.resolve_path("project/main.py")
    assert resolved == sandbox.root / "project" / "main.py"


def test_resolve_absolute_path_within_workspace(sandbox):
    target = sandbox.root / "file.txt"
    assert sandbox.resolve_path(str(target)) == target


def test_resolve_rejects_traversal_outside_workspace(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.resolve_path("../outside.txt")


def test_resolve_rejects_absolute_path_outside_workspace(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.resolve_path("/etc/passwd")


def test_resolve_rejects_empty_path(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.resolve_path("   ")


def test_check_command_allows_safe_relative_command(sandbox):
    sandbox.check_command("ls -la project/")


def test_check_command_rejects_traversal(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.check_command("cat ../../etc/passwd")


def test_check_command_rejects_absolute_path_outside_workspace(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.check_command("cat /etc/passwd")


def test_check_command_allows_absolute_path_within_workspace(sandbox):
    sandbox.check_command(f"cat {sandbox.root}/file.txt")


def test_check_command_rejects_root_access(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.check_command("ls /")


def test_check_command_rejects_cd_outside_workspace(sandbox):
    with pytest.raises(SandboxViolationError):
        sandbox.check_command("cd /tmp && ls")


def test_check_command_allows_cd_within_workspace(sandbox):
    sandbox.check_command(f"cd {sandbox.root}/project && ls")
