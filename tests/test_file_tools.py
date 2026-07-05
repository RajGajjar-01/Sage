from app.core.sandbox import Sandbox
from app.services.file_tools import FileTools


def _tools(tmp_path):
    return FileTools(Sandbox(tmp_path / "workspace"))


def test_write_then_read_file(tmp_path):
    tools = _tools(tmp_path)

    write_result = tools.write_file("main.py", "print('hi')")
    assert write_result.success
    assert "created" in write_result.output

    read_result = tools.read_file("main.py")
    assert read_result.success
    assert "print('hi')" in read_result.output


def test_write_file_reports_modified_on_second_write(tmp_path):
    tools = _tools(tmp_path)
    tools.write_file("main.py", "a")

    result = tools.write_file("main.py", "b")

    assert "modified" in result.output


def test_read_missing_file_fails(tmp_path):
    tools = _tools(tmp_path)
    result = tools.read_file("missing.py")
    assert not result.success


def test_read_file_rejects_path_outside_workspace(tmp_path):
    tools = _tools(tmp_path)
    result = tools.read_file("../outside.py")
    assert not result.success
    assert "Error" in result.output


def test_list_dir_reports_files_and_dirs(tmp_path):
    tools = _tools(tmp_path)
    tools.write_file("a.txt", "x")
    tools.create_dir("sub")

    result = tools.list_dir(".")

    assert result.success
    assert "a.txt" in result.output
    assert "sub/" in result.output


def test_create_dir_is_idempotent(tmp_path):
    tools = _tools(tmp_path)
    tools.create_dir("sub")
    result = tools.create_dir("sub")
    assert result.success
    assert "already exists" in result.output


def test_delete_file_removes_file(tmp_path):
    tools = _tools(tmp_path)
    tools.write_file("a.txt", "x")

    result = tools.delete_file("a.txt")

    assert result.success
    assert tools.read_file("a.txt").success is False


def test_delete_directory_recursively(tmp_path):
    tools = _tools(tmp_path)
    tools.write_file("sub/a.txt", "x")

    result = tools.delete_file("sub")

    assert result.success
    assert not tools.list_dir("sub").success


def test_delete_missing_path_fails(tmp_path):
    tools = _tools(tmp_path)
    result = tools.delete_file("missing")
    assert not result.success


def test_parse_and_execute_read_file_tag(tmp_path):
    tools = _tools(tmp_path)
    tools.write_file("a.txt", "hello")

    result, remaining = tools.parse_and_execute("<read_file>a.txt</read_file>")

    assert result.success
    assert remaining == ""


def test_parse_and_execute_write_file_double_quotes(tmp_path):
    tools = _tools(tmp_path)

    result, _ = tools.parse_and_execute('<write_file path="a.txt">hello</write_file>')

    assert result.success
    assert tools.read_file("a.txt").output.endswith("hello")


def test_parse_and_execute_write_file_single_quotes(tmp_path):
    tools = _tools(tmp_path)

    result, _ = tools.parse_and_execute("<write_file path='a.txt'>hello</write_file>")

    assert result.success


def test_parse_and_execute_unknown_when_no_tag(tmp_path):
    tools = _tools(tmp_path)
    result, remaining = tools.parse_and_execute("just some text")
    assert not result.success
    assert remaining == "just some text"
