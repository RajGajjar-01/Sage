import aiosqlite
import pytest

from app.core.config import Settings
from app.core.database import _SCHEMA
from app.core.sandbox import Sandbox
from app.services.doc_cache import DocCache
from app.services.prompt_enhancer import (
    PromptEnhancer,
    _parse_tavily_response,
    is_already_detailed,
    is_meta_command,
)


@pytest.fixture
async def connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.mark.parametrize(
    "user_input",
    [
        "x" * 301,
        "line1\nline2\nline3\nline4\nline5\nline6",
        "please fix src/app.py",
        "```python\nprint(1)\n```",
    ],
)
def test_is_already_detailed_true_cases(user_input):
    assert is_already_detailed(user_input)


def test_is_already_detailed_false_for_vague_request():
    assert not is_already_detailed("build me a todo app")


@pytest.mark.parametrize(
    "user_input", ["/plan do something", "exit", "yes", "ok", "abc"]
)
def test_is_meta_command_true_cases(user_input):
    assert is_meta_command(user_input)


def test_is_meta_command_false_for_real_request():
    assert not is_meta_command("build me a todo app with fastapi")


def test_parse_tavily_response_extracts_answer_and_results():
    raw = '{"answer": "Use FastAPI.", "results": [{"title": "FastAPI docs", "content": "Modern web framework"}]}'
    parsed = _parse_tavily_response(raw)
    assert "Use FastAPI." in parsed
    assert "FastAPI docs" in parsed


def test_parse_tavily_response_handles_invalid_json():
    assert _parse_tavily_response("not json") == "(Could not parse search results)"


@pytest.mark.asyncio
async def test_enhance_skips_without_groq_key(tmp_path, connection):
    settings = Settings(GROQ_API_KEY=None, ZHIPU_API_KEY=None)
    sandbox = Sandbox(tmp_path / "workspace")
    enhancer = PromptEnhancer(settings, sandbox, DocCache(connection))

    result, was_enhanced = await enhancer.enhance("build me a todo app")

    assert result == "build me a todo app"
    assert was_enhanced is False


@pytest.mark.asyncio
async def test_enhance_skips_meta_commands(tmp_path, connection):
    settings = Settings(GROQ_API_KEY="key", ZHIPU_API_KEY=None)
    sandbox = Sandbox(tmp_path / "workspace")
    enhancer = PromptEnhancer(settings, sandbox, DocCache(connection))

    result, was_enhanced = await enhancer.enhance("yes")

    assert result == "yes"
    assert was_enhanced is False


def test_groq_client_uses_configured_endpoint(tmp_path, connection):
    settings = Settings(
        GROQ_API_KEY="key",
        ZHIPU_API_KEY=None,
        GROQ_ENDPOINT="https://proxy.internal/v1/",
    )
    sandbox = Sandbox(tmp_path / "workspace")
    enhancer = PromptEnhancer(settings, sandbox, DocCache(connection))

    assert str(enhancer._groq_client.base_url) == "https://proxy.internal/v1/"
