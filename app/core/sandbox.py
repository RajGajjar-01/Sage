import os
import re
from pathlib import Path

_TOKEN = re.compile(r"[^\s'\"`;&|()<>]+")
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

    def _resolve_relative_to_root(self, raw: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        candidate = Path(expanded)
        return candidate if candidate.is_absolute() else self.root / candidate

    def check_command(self, command: str) -> None:
        """Raise if a shell command references a path outside the workspace.

        Expands ~/$VAR per token and resolves symlinks (via contains()) before
        the containment check, so both variable-expanded absolute paths and
        relative paths that traverse a symlink out of the workspace are caught.
        """
        stripped = command.strip()
        if not stripped:
            raise SandboxViolationError("Empty command")
        if ".." in stripped:
            raise SandboxViolationError("Directory traversal not allowed")

        for raw_token in _TOKEN.findall(stripped):
            if "://" in raw_token:
                continue
            expanded = os.path.expandvars(os.path.expanduser(raw_token))
            if expanded == "/":
                raise SandboxViolationError("Root '/' access not allowed")
            if expanded.startswith("/") or raw_token.startswith("~") or "/" in expanded:
                full = self._resolve_relative_to_root(raw_token)
                if not self.contains(full):
                    raise SandboxViolationError(f"Path outside workspace: {raw_token}")

        for cd_match in _CD_TARGET.finditer(stripped):
            raw_target = cd_match.group(1).strip("\"'`")
            full = self._resolve_relative_to_root(raw_target)
            if not self.contains(full):
                raise SandboxViolationError(
                    f"cd target outside workspace: {raw_target}"
                )
