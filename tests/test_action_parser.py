from app.services.action_parser import (
    ActionType,
    extract,
    get_action_type,
    has_file_tool,
    is_exit,
    is_read_only_command,
)


def test_extract_returns_bash_block_contents():
    output = "Some text\n```bash\nls -la\n```\nmore text"
    assert extract(output) == "ls -la"


def test_extract_returns_none_without_block():
    assert extract("just plain text") is None


def test_extract_normalizes_crlf():
    output = "```bash\r\nls -la\r\n```"
    assert extract(output) == "ls -la"


def test_is_exit_case_insensitive():
    assert is_exit("Exit")
    assert is_exit("  exit  ")
    assert not is_exit("exit 1")


def test_has_file_tool_detects_read_file_tag():
    assert has_file_tool("<read_file>main.py</read_file>")
    assert not has_file_tool("```bash\nls\n```")


def test_get_action_type_prefers_file_tool_over_bash():
    output = '<write_file path="a.py">x</write_file>\n```bash\nls\n```'
    assert get_action_type(output) == ActionType.FILE_TOOL


def test_get_action_type_bash_when_no_file_tool():
    assert get_action_type("```bash\nls\n```") == ActionType.BASH_COMMAND


def test_get_action_type_none_when_nothing_matches():
    assert get_action_type("just chatting") == ActionType.NONE


def test_is_read_only_command_allows_known_prefixes():
    assert is_read_only_command("ls -la && cat file.txt")


def test_is_read_only_command_rejects_write_commands():
    assert not is_read_only_command("rm -rf build")


def test_is_read_only_command_rejects_uv_and_npx():
    assert not is_read_only_command("uv add flask")
    assert not is_read_only_command("npx create-react-app")


def test_is_read_only_command_rejects_mixed_chain():
    assert not is_read_only_command("ls && rm -rf /")
