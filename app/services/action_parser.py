import re
from enum import Enum, auto

COMMAND_BLOCK = re.compile(r"```(?:bash-action|bash|sh)\s*\n?(.*?)\n?```", re.DOTALL)
_FILE_TOOL_PATTERN = re.compile(
    r"<(read_file|write_file|list_dir|create_dir|delete_file)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)

READ_ONLY_PREFIXES = frozenset(
    {
        "ls", "find", "tree", "cat", "head", "tail", "wc", "file", "stat",
        "grep", "rg", "pwd", "echo", "which", "du", "df", "uname", "date",
        "realpath", "basename", "dirname", "diff",
    }
)  # fmt: skip


class ActionType(Enum):
    NONE = auto()
    BASH_COMMAND = auto()
    FILE_TOOL = auto()


def extract(llm_output: str) -> str | None:
    """Pull the first fenced bash/sh block out of an LLM response, if any."""
    match = COMMAND_BLOCK.search(llm_output)
    if not match:
        return None
    command = match.group(1).replace("\r\n", "\n").replace("\r", "\n").strip()
    return command or None


def is_exit(command: str) -> bool:
    return command.strip().lower() == "exit"


def has_file_tool(llm_output: str) -> bool:
    return bool(_FILE_TOOL_PATTERN.search(llm_output))


def get_action_type(llm_output: str) -> ActionType:
    if has_file_tool(llm_output):
        return ActionType.FILE_TOOL
    if extract(llm_output) is not None:
        return ActionType.BASH_COMMAND
    return ActionType.NONE


_WRITE_INDICATORS = re.compile(r">|\btee\b|`|\$\(|<\(")
_CHAIN_SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\n|&|\|)\s*")
_DANGEROUS_FLAGS = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf"}
)


def is_read_only_command(command: str) -> bool:
    """Whether every chained sub-command is on the read-only allowlist.

    This is a lexical heuristic, not a real shell parser: it splits on the
    chain/pipe/background operators bash itself recognizes and rejects any
    write-indicating syntax, but it cannot see every possible bypass shape
    (e.g. exotic quoting). Prefer classifying as non-read-only when unsure.
    """
    if _WRITE_INDICATORS.search(command):
        return False

    parts = _CHAIN_SEPARATORS.split(command)
    for part in parts:
        trimmed = part.strip()
        if not trimmed:
            continue
        words = trimmed.split()
        first_word = words[0].rsplit("/", 1)[-1].lower()
        if first_word not in READ_ONLY_PREFIXES:
            return False
        if any(w in _DANGEROUS_FLAGS for w in words[1:]):
            return False
    return True
