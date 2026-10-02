import aiosqlite
import pytest

from app.core.config import Settings
from app.core.database import _SCHEMA
from app.core.sandbox import Sandbox
from app.models.agent import Message
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository
from app.services.file_tools import FileTools
from app.services.llm_service import LlmMetrics, TokenUsage
from app.services.orchestrator import AgentOrchestrator, SessionOutcome
from app.services.shell_executor import ShellExecutor


class FakeLlm:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, history, system_prompt):
        self.calls.append(list(history))
        response = self._responses.pop(0)
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        metrics = LlmMetrics("FAKE", "fake-model", 1.0, 2.0, usage)
        return response, usage, metrics


class FakeUI:
    def __init__(self, confirm_answers: list[bool] | None = None) -> None:
        self.assistant_messages: list[str] = []
        self.results: list[tuple[bool, str]] = []
        self.notifications: list[str] = []
        self.commands: list[str] = []
        self._confirm_answers = confirm_answers or []

    async def on_assistant_message(self, text, usage, metrics):
        self.assistant_messages.append(text)

    async def on_command_panel(self, command):
        self.commands.append(command)

    async def on_tool_panel(self, kind, title):
        pass

    async def on_result(self, success, summary):
        self.results.append((success, summary))

    async def notify(self, message):
        self.notifications.append(message)

    async def confirm(self, prompt, default=True):
        return self._confirm_answers.pop(0) if self._confirm_answers else default


@pytest.fixture
async def connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


def _settings():
    return Settings(
        GROQ_API_KEY=None, ZHIPU_API_KEY=None, MAX_AGENT_STEPS=25, DOOM_LOOP_THRESHOLD=3
    )


def _orchestrator(tmp_path, connection, llm, ui, settings=None, prompt_enhancer=None):
    sandbox = Sandbox(tmp_path / "workspace")
    return AgentOrchestrator(
        sandbox=sandbox,
        llm=llm,
        shell=ShellExecutor(sandbox, timeout_seconds=5),
        file_tools=FileTools(sandbox),
        prompt_enhancer=prompt_enhancer or _NoOpEnhancer(),
        sessions=SessionRepository(connection),
        messages=MessageRepository(connection),
        executions=ExecutionRepository(connection),
        ui=ui,
        settings=settings or _settings(),
    )


class _NoOpEnhancer:
    async def enhance(self, user_input: str) -> tuple[str, bool]:
        return user_input, False


class _BrokenEnhancer:
    async def enhance(self, user_input: str) -> tuple[str, bool]:
        raise RuntimeError("network blip")


@pytest.mark.asyncio
async def test_plain_response_ends_turn_with_continue(tmp_path, connection):
    llm = FakeLlm(["Just chatting, no action needed."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("hello")

    assert outcome is SessionOutcome.CONTINUE
    assert ui.assistant_messages == ["Just chatting, no action needed."]


@pytest.mark.asyncio
async def test_exit_command_without_plan_ends_session(tmp_path, connection):
    llm = FakeLlm(["Done for now.\n```bash\nexit\n```"])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("hello")

    assert outcome is SessionOutcome.ENDED


@pytest.mark.asyncio
async def test_read_only_command_runs_without_confirmation(tmp_path, connection):
    llm = FakeLlm(["```bash\nls\n```", "All done, no more actions."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("list files")

    assert outcome is SessionOutcome.CONTINUE
    assert ui.commands == ["ls"]
    assert ui.results[0][0] is True


@pytest.mark.asyncio
async def test_non_read_only_command_requires_confirmation(tmp_path, connection):
    llm = FakeLlm(["```bash\necho hi > out.txt\n```", "Wrote the file."])
    ui = FakeUI(confirm_answers=[True])
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("write a file")

    assert outcome is SessionOutcome.CONTINUE
    assert (tmp_path / "workspace" / "out.txt").exists()


@pytest.mark.asyncio
async def test_declined_confirmation_stops_the_turn(tmp_path, connection):
    llm = FakeLlm(["```bash\necho hi > out.txt\n```"])
    ui = FakeUI(confirm_answers=[False])
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("write a file")

    assert outcome is SessionOutcome.CONTINUE
    assert not (tmp_path / "workspace" / "out.txt").exists()


@pytest.mark.asyncio
async def test_sandbox_violation_is_reported_and_loop_continues(tmp_path, connection):
    llm = FakeLlm(["```bash\ncat /etc/passwd\n```", "Understood, blocked."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("read a system file")

    assert outcome is SessionOutcome.CONTINUE
    assert any("Blocked" in r[1] for r in ui.results)


@pytest.mark.asyncio
async def test_doom_loop_detection_stops_after_threshold(tmp_path, connection):
    llm = FakeLlm(["```bash\necho hi\n```"] * 3)
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("say hi repeatedly")

    assert outcome is SessionOutcome.CONTINUE
    assert any("Repeating" in n for n in ui.notifications)
    assert len(llm.calls) == 3


@pytest.mark.asyncio
async def test_file_tool_writes_via_sandbox(tmp_path, connection):
    llm = FakeLlm(['<write_file path="app.py">print(1)</write_file>', "Wrote app.py."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("create app.py")

    assert outcome is SessionOutcome.CONTINUE
    assert (tmp_path / "workspace" / "app.py").read_text() == "print(1)"


@pytest.mark.asyncio
async def test_plan_approval_continues_into_execution(tmp_path, connection):
    llm = FakeLlm(
        [
            "## Plan\n\nDo the thing.\n```bash\nexit\n```",
            "Executed the plan.",
        ]
    )
    ui = FakeUI(confirm_answers=[True])
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("build me something")

    assert outcome is SessionOutcome.CONTINUE
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_resume_session_reloads_history(tmp_path, connection):
    llm = FakeLlm(["Just chatting."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    session = await orchestrator.start_session("test session")
    await orchestrator.send_message("hello")

    resumed_llm = FakeLlm(["Still chatting."])
    resumed = _orchestrator(tmp_path, connection, resumed_llm, FakeUI())
    loaded_session = await resumed.resume_session(session.id)

    assert loaded_session.id == session.id
    assert len(resumed._history) == 2


@pytest.mark.asyncio
async def test_explicit_exit_command_marks_session_completed(tmp_path, connection):
    llm = FakeLlm([])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    session = await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("exit")

    assert outcome is SessionOutcome.ENDED
    updated = await orchestrator.sessions.get(session.id)
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_plan_approval_does_not_reset_step_budget(tmp_path, connection):
    llm = FakeLlm(["## Plan\n\nDo it.\n```bash\nexit\n```", "Done."])
    ui = FakeUI(confirm_answers=[True])
    settings = _settings()
    settings.MAX_AGENT_STEPS = 1
    orchestrator = _orchestrator(tmp_path, connection, llm, ui, settings=settings)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("build me something")

    assert outcome is SessionOutcome.CONTINUE
    assert len(llm.calls) == 1
    assert any("Reached" in n for n in ui.notifications)


@pytest.mark.asyncio
async def test_sh_fence_is_stripped_from_assistant_text(tmp_path, connection):
    llm = FakeLlm(["Here's what I'll do.\n```sh\nls\n```", "Done."])
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, llm, ui)
    await orchestrator.start_session("test session")

    await orchestrator.send_message("list files")

    assert ui.assistant_messages[0] == "Here's what I'll do."


@pytest.mark.asyncio
async def test_enhancer_failure_falls_back_to_original_input(tmp_path, connection):
    llm = FakeLlm(["Just chatting, no action needed."])
    ui = FakeUI()
    orchestrator = _orchestrator(
        tmp_path, connection, llm, ui, prompt_enhancer=_BrokenEnhancer()
    )
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("hello")

    assert outcome is SessionOutcome.CONTINUE
    assert llm.calls[0][-1].content == "hello"


@pytest.mark.asyncio
async def test_send_message_without_llm_asks_to_connect(tmp_path, connection):
    ui = FakeUI()
    orchestrator = _orchestrator(tmp_path, connection, None, ui)
    await orchestrator.start_session("test session")

    outcome = await orchestrator.send_message("hello")

    assert outcome is SessionOutcome.CONTINUE
    assert any("/connect" in n for n in ui.notifications)


@pytest.mark.asyncio
async def test_resume_reactivates_a_completed_session(tmp_path, connection):
    orchestrator = _orchestrator(tmp_path, connection, FakeLlm(["Done."]), FakeUI())
    session = await orchestrator.start_session("t")
    await orchestrator.send_message("hi")
    assert await orchestrator.send_message("exit") is SessionOutcome.ENDED
    assert (await orchestrator.sessions.get(session.id)).status == "completed"

    resumed = await orchestrator.resume_session(session.id)

    assert resumed.status == "active"
    assert (await orchestrator.sessions.get(session.id)).status == "active"
    assert [m.role for m in orchestrator.history] == ["user", "assistant"]
