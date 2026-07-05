import re
from dataclasses import dataclass
from enum import Enum, auto
from importlib import resources
from typing import Protocol

from app.core.config import Settings
from app.core.sandbox import Sandbox, SandboxViolationError
from app.models.agent import Execution, Message, Session
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository
from app.services.action_parser import (
    COMMAND_BLOCK,
    ActionType,
    extract,
    get_action_type,
    is_exit,
    is_read_only_command,
)
from app.services.file_tools import FileTools
from app.services.llm_service import LlmMetrics, LlmService, TokenUsage
from app.services.prompt_enhancer import PromptEnhancer
from app.services.shell_executor import ShellExecutor

_MAX_HISTORY_MESSAGES = 20
_MAX_TOOL_OUTPUT_CHARS = 2000
_TRUNCATED_ERROR_TAIL_CHARS = 800


class SessionOutcome(Enum):
    CONTINUE = auto()
    ENDED = auto()


class AgentUI(Protocol):
    """Presentation hooks the orchestrator calls into; the CLI implements these with Rich."""

    async def on_assistant_message(
        self, text: str, usage: TokenUsage, metrics: LlmMetrics
    ) -> None: ...
    async def on_command_panel(self, command: str) -> None: ...
    async def on_tool_panel(self, kind: str, title: str) -> None: ...
    async def on_result(self, success: bool, summary: str) -> None: ...
    async def notify(self, message: str) -> None: ...
    async def confirm(self, prompt: str, default: bool = True) -> bool: ...


@dataclass
class AgentOrchestrator:
    """Drives the think -> act -> observe loop: LLM call, then bash/file-tool execution."""

    sandbox: Sandbox
    llm: LlmService
    shell: ShellExecutor
    file_tools: FileTools
    prompt_enhancer: PromptEnhancer
    sessions: SessionRepository
    messages: MessageRepository
    executions: ExecutionRepository
    ui: AgentUI
    settings: Settings

    def __post_init__(self) -> None:
        self._system_prompt = (
            resources.files("app.prompts").joinpath("system_prompt.txt").read_text()
        )
        self._session: Session | None = None
        self._history: list[Message] = []

    async def start_session(self, title: str) -> Session:
        self._session = await self.sessions.create(title)
        self._history = []
        return self._session

    async def resume_session(self, session_id: str) -> Session:
        session = await self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found.")
        self._session = session
        self._history = await self.messages.list_by_session(session_id)
        return session

    async def send_message(self, user_input: str) -> SessionOutcome:
        if self._session is None:
            raise RuntimeError(
                "No active session — call start_session or resume_session first."
            )

        if user_input.strip().lower() in ("exit", "/exit"):
            await self.sessions.update_status(self._session.id, "completed")
            return SessionOutcome.ENDED

        is_first_message = not any(m.role == "user" for m in self._history)
        enhanced_input = user_input
        if is_first_message:
            try:
                enhanced, was_enhanced = await self.prompt_enhancer.enhance(user_input)
            except Exception:
                enhanced, was_enhanced = user_input, False
            if was_enhanced and await self.ui.confirm(
                f"Use enhanced prompt?\n\n{enhanced}", default=True
            ):
                enhanced_input = enhanced

        await self._append_message(
            Message(session_id=self._session.id, role="user", content=enhanced_input)
        )
        return await self._agent_loop()

    async def _agent_loop(self) -> SessionOutcome:
        assert self._session is not None
        recent_commands: list[str] = []

        for _step in range(self.settings.MAX_AGENT_STEPS):
            try:
                response, usage, metrics = await self.llm.complete(
                    self._history[-_MAX_HISTORY_MESSAGES:], self._build_system_prompt()
                )
            except Exception as exc:
                await self.ui.notify(f"LLM error: {exc}")
                return SessionOutcome.CONTINUE

            text_part = _extract_text_part(response)
            if text_part:
                await self.ui.on_assistant_message(text_part, usage, metrics)

            await self._append_message(
                Message(session_id=self._session.id, role="assistant", content=response)
            )
            await self.sessions.touch(self._session.id)

            action_type = get_action_type(response)
            if action_type is ActionType.NONE:
                return SessionOutcome.CONTINUE

            if action_type is ActionType.FILE_TOOL:
                await self._run_file_tool(response)
                continue

            command = extract(response)
            assert command is not None

            if is_exit(command):
                outcome = await self._handle_exit(text_part)
                if outcome is not None:
                    return outcome
                continue  # plan approved — keep executing within this same step/doom-loop budget

            trimmed = command.strip()
            recent_commands.append(trimmed)
            if len(recent_commands) > self.settings.DOOM_LOOP_THRESHOLD:
                recent_commands.pop(0)
            if (
                len(recent_commands) == self.settings.DOOM_LOOP_THRESHOLD
                and len(set(recent_commands)) == 1
            ):
                await self.ui.notify(
                    f"Repeating the same command {self.settings.DOOM_LOOP_THRESHOLD}x. Returning control."
                )
                return SessionOutcome.CONTINUE

            await self.ui.on_command_panel(command)

            if not await self._run_shell_command(command, trimmed):
                return SessionOutcome.CONTINUE

        await self.ui.notify(
            f"Reached {self.settings.MAX_AGENT_STEPS} steps. Returning control."
        )
        return SessionOutcome.CONTINUE

    async def _run_file_tool(self, response: str) -> None:
        assert self._session is not None
        result, _ = self.file_tools.parse_and_execute(response)
        await self.ui.on_tool_panel("file tool", result.tool_name)
        await self.ui.on_result(result.success, result.output.split("\n")[0])
        await self._append_message(
            Message(
                session_id=self._session.id, role="tool_result", content=result.output
            )
        )

    async def _run_shell_command(self, command: str, trimmed: str) -> bool:
        """Execute (or block) a bash command. Returns False if the loop should pause for the user."""
        assert self._session is not None

        if not is_read_only_command(command):
            confirmed = await self.ui.confirm("Execute?", default=True)
            if not confirmed:
                await self._append_message(
                    Message(
                        session_id=self._session.id,
                        role="tool_result",
                        content="User skipped this command.",
                    )
                )
                return False

        try:
            result = await self.shell.run(command)
        except SandboxViolationError as exc:
            await self.ui.on_result(False, f"Blocked: {exc}")
            await self._append_message(
                Message(
                    session_id=self._session.id,
                    role="tool_result",
                    content=f"ERROR: Blocked by sandbox. {exc}",
                )
            )
            return True

        await self.executions.save(
            Execution(
                session_id=self._session.id,
                command=command,
                output=result.output,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
            )
        )

        await self.ui.on_result(
            result.exit_code == 0, f"exit {result.exit_code} · {result.duration_ms}ms"
        )

        content = (
            "Command executed successfully. No output."
            if not result.output
            else _truncate_output(result.output, result.exit_code)
        )
        await self._append_message(
            Message(session_id=self._session.id, role="tool_result", content=content)
        )
        return True

    async def _handle_exit(self, text_part: str) -> SessionOutcome | None:
        """Handle an `exit` bash action. Returns None to keep looping (plan approved)."""
        assert self._session is not None

        if "## Plan" in text_part:
            if await self.ui.confirm(
                "Plan ready. Approve and start executing?", default=True
            ):
                await self._append_message(
                    Message(
                        session_id=self._session.id,
                        role="user",
                        content="Plan approved. Start executing step by step.",
                    )
                )
                return None
            return SessionOutcome.CONTINUE

        await self.sessions.update_status(self._session.id, "completed")
        return SessionOutcome.ENDED

    async def _append_message(self, message: Message) -> None:
        saved = await self.messages.save(message)
        self._history.append(saved)

    def _build_system_prompt(self) -> str:
        assert self._session is not None
        first_user_message = next(
            (m.content for m in self._history if m.role == "user"), None
        )
        task_context = (
            f"\n\n=== USER'S ORIGINAL TASK ===\n{first_user_message}\n"
            if first_user_message
            else ""
        )
        env_context = f"\n\n=== ENVIRONMENT ===\nWorking directory: {self.shell.working_directory}\n"
        return self._system_prompt + task_context + env_context


def _extract_text_part(response: str) -> str:
    text = COMMAND_BLOCK.sub("", response)
    text = re.sub(
        r"<(write_file|read_file|list_dir|create_dir|delete_file)\b[^>]*>[\s\S]*?</\1>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_output(output: str, exit_code: int) -> str:
    if len(output) <= _MAX_TOOL_OUTPUT_CHARS:
        return output
    if exit_code != 0:
        return f"[Truncated — last {_TRUNCATED_ERROR_TAIL_CHARS} chars]\n...{output[-_TRUNCATED_ERROR_TAIL_CHARS:]}"
    half = _MAX_TOOL_OUTPUT_CHARS // 2
    return f"{output[:half]}\n\n... [{len(output) - _MAX_TOOL_OUTPUT_CHARS} chars omitted] ...\n\n{output[-half:]}"
