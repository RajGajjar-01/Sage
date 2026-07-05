import re
from enum import Enum, auto

_COMMAND_BLOCK = re.compile(r"```(?:bash-action|bash|sh)\s*\n?(.*?)\n?```", re.DOTALL)
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
    match = _COMMAND_BLOCK.search(llm_output)
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


def is_read_only_command(command: str) -> bool:
    """Whether every chained sub-command is on the read-only allowlist."""
    parts = re.split(r"\s*(?:&&|;|\|\|)\s*", command)
    for part in parts:
        trimmed = part.strip()
        if not trimmed:
            continue
        first_word = trimmed.split()[0].rsplit("/", 1)[-1].lower()
        if first_word not in READ_ONLY_PREFIXES:
            return False
    return True
