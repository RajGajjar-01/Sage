import re
import shutil
from dataclasses import dataclass

from app.core.sandbox import Sandbox

_READ = re.compile(r"<read_file>\s*(.+?)\s*</read_file>", re.DOTALL)
_WRITE = re.compile(
    r"""<write_file\s+path=(["'])(.+?)\1\s*>(.*?)</write_file>""", re.DOTALL
)
_LIST = re.compile(r"<list_dir>\s*(.+?)\s*</list_dir>", re.DOTALL)
_CREATE = re.compile(r"<create_dir>\s*(.+?)\s*</create_dir>", re.DOTALL)
_DELETE = re.compile(r"<delete_file>\s*(.+?)\s*</delete_file>", re.DOTALL)

_SIZE_SUFFIXES = ("B", "KB", "MB", "GB", "TB")


@dataclass(frozen=True)
class FileToolResult:
    tool_name: str
    success: bool
    output: str
    file_path: str | None = None


class FileTools:
    """Sandboxed read/write/list/create/delete tools exposed to the LLM as XML-ish tags.

    Every method reports failure as an unsuccessful FileToolResult rather than
    raising, so a bad path, a binary file, or a permission error never breaks
    the agent loop.
    """

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def parse_and_execute(self, output: str) -> FileToolResult:
        """Run the first file-tool command found in `output`."""
        if match := _READ.search(output):
            return self.read_file(match.group(1).strip())
        if match := _WRITE.search(output):
            return self.write_file(match.group(2).strip(), match.group(3))
        if match := _LIST.search(output):
            return self.list_dir(match.group(1).strip())
        if match := _CREATE.search(output):
            return self.create_dir(match.group(1).strip())
        if match := _DELETE.search(output):
            return self.delete_file(match.group(1).strip())
        return FileToolResult("unknown", False, "No file tool command found")

    def read_file(self, relative_path: str) -> FileToolResult:
        try:
            path = self._sandbox.resolve_path(relative_path)
            if not path.is_file():
                return FileToolResult(
                    "read_file",
                    False,
                    f"File not found: {relative_path}\nResolved path: {path}",
                )
            content = path.read_text()
        except Exception as exc:
            return FileToolResult("read_file", False, f"Error reading file: {exc}")

        header = f"File: {relative_path} ({len(content)} chars)\n{'─' * 40}\n"
        return FileToolResult("read_file", True, header + content, str(path))

    def write_file(self, relative_path: str, content: str) -> FileToolResult:
        try:
            path = self._sandbox.resolve_path(relative_path)
            existed = path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        except Exception as exc:
            return FileToolResult("write_file", False, f"Error writing file: {exc}")

        action = "modified" if existed else "created"
        return FileToolResult(
            "write_file",
            True,
            f"File {action}: {relative_path} ({len(content)} chars written)",
            str(path),
        )

    def list_dir(self, relative_path: str) -> FileToolResult:
        try:
            path = self._sandbox.resolve_path(relative_path)
            if not path.is_dir():
                return FileToolResult(
                    "list_dir", False, f"Directory not found: {relative_path}"
                )
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            lines = [f"Directory: {relative_path}", "─" * 40]
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"\U0001f4c1 {entry.name}/")
                else:
                    lines.append(
                        f"\U0001f4c4 {entry.name} ({_format_size(entry.stat().st_size)})"
                    )
        except Exception as exc:
            return FileToolResult("list_dir", False, f"Error listing directory: {exc}")

        lines.append(f"\n{len(entries)} items total")
        return FileToolResult("list_dir", True, "\n".join(lines))

    def create_dir(self, relative_path: str) -> FileToolResult:
        try:
            path = self._sandbox.resolve_path(relative_path)
            if path.is_dir():
                return FileToolResult(
                    "create_dir", True, f"Directory already exists: {relative_path}"
                )
            path.mkdir(parents=True)
        except Exception as exc:
            return FileToolResult(
                "create_dir", False, f"Error creating directory: {exc}"
            )

        return FileToolResult(
            "create_dir", True, f"Directory created: {relative_path}", str(path)
        )

    def delete_file(self, relative_path: str) -> FileToolResult:
        try:
            path = self._sandbox.resolve_path(relative_path)
            if path.is_file():
                path.unlink()
                return FileToolResult(
                    "delete_file", True, f"File deleted: {relative_path}", str(path)
                )
            if path.is_dir():
                shutil.rmtree(path)
                return FileToolResult(
                    "delete_file",
                    True,
                    f"Directory deleted: {relative_path}",
                    str(path),
                )
        except Exception as exc:
            return FileToolResult("delete_file", False, f"Error deleting: {exc}")

        return FileToolResult(
            "delete_file", False, f"File or directory not found: {relative_path}"
        )


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for suffix in _SIZE_SUFFIXES:
        if size < 1024 or suffix == _SIZE_SUFFIXES[-1]:
            return f"{int(size)}B" if suffix == "B" else f"{size:.1f}{suffix}"
        size /= 1024
    raise AssertionError("unreachable")
