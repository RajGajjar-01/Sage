import re
from pathlib import Path

_ABS_PATH_TOKEN = re.compile(r"(?<![\w./-])/(?:[^\s'\"`\\]|\\\s)*")
_CD_TARGET = re.compile(r"\bcd\s+([^\s;&|]+)")


class SandboxViolationError(Exception):
    """Raised when a path or command would escape the configured workspace root."""


class Sandbox:
    """Confines file and shell path access to a single workspace root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def contains(self, candidate: Path) -> bool:
        resolved = candidate.expanduser().resolve()
        return resolved == self.root or self.root in resolved.parents

    def resolve_path(self, relative_or_absolute: str) -> Path:
        """Resolve a user-supplied path, raising if it escapes the workspace root."""
        raw = relative_or_absolute.strip()
        if not raw:
            raise SandboxViolationError("Path cannot be empty")

        candidate = Path(raw)
        full = candidate if candidate.is_absolute() else self.root / candidate
        full = full.resolve()

        if not self.contains(full):
            raise SandboxViolationError(
                f"Path outside workspace: {raw} (resolved: {full})"
            )
        return full

    def check_command(self, command: str) -> None:
        """Raise if a shell command references an absolute path outside the workspace."""
        stripped = command.strip()
        if not stripped:
            raise SandboxViolationError("Empty command")
        if ".." in stripped:
            raise SandboxViolationError("Directory traversal not allowed")

        for match in _ABS_PATH_TOKEN.finditer(stripped):
            token = match.group().rstrip(";&|)]}")
            if token == "/":
                raise SandboxViolationError("Root '/' access not allowed")
            if not self.contains(Path(token)):
                raise SandboxViolationError(f"Path outside workspace: {token}")

        cd_match = _CD_TARGET.search(stripped)
        if cd_match:
            target = cd_match.group(1).strip("\"'`")
            if Path(target).is_absolute() and not self.contains(Path(target)):
                raise SandboxViolationError(f"cd target outside workspace: {target}")
