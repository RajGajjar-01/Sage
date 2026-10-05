import asyncio
from datetime import datetime
from importlib.metadata import version as package_version

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from app.cli.banner import banner
from app.cli.connect import KNOWN_PROVIDERS, Choice, connect_provider
from app.models.agent import Message
from app.models.provider import ProviderCredential
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import (
    LlmMetrics,
    LlmService,
    ModelInfo,
    TokenUsage,
    list_models,
)
from app.services.orchestrator import (
    AgentOrchestrator,
    SessionOutcome,
    extract_text_part,
)

GOLD = "#F0AA00"
_TRANSCRIPT_MESSAGES = 10
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

COMMANDS = [
    Choice("New chat", "/new", "/new"),
    Choice("Resume a chat", "/sessions", "/sessions"),
    Choice("Switch model", "/model", "/model"),
    Choice("Connect a provider", "/connect", "/connect"),
    Choice("Help", "/help", "/help"),
    Choice("Exit", "/exit", "/exit"),
]
_HELP = "  ".join(f"[b]{c.value}[/] [dim]{c.label.lower()}[/]" for c in COMMANDS)

CSS = f"""
Screen {{ background: #0a0a0a; }}
#main {{ width: 1fr; padding: 1 2 0 2; }}
#log {{ height: 1fr; scrollbar-size-vertical: 1; }}
#log > * {{ margin-bottom: 1; }}
.user {{ border-left: thick {GOLD}; background: #161616; padding: 1 2; }}
.meta {{ color: #808080; padding-left: 1; }}
.tool {{ border-left: thick #3a3a3a; background: #111111; padding: 0 2; }}
.ok {{ color: #5fd75f; padding-left: 1; }}
.fail {{ color: #ff5f5f; padding-left: 1; }}
.notice {{ color: {GOLD}; padding-left: 1; }}
#composer {{ height: auto; border-left: thick {GOLD}; background: #161616; padding: 1 2; }}
#prompt, #prompt:focus {{ border: none; background: #161616; padding: 0; height: 1; }}
#model-line {{ margin-top: 1; color: #808080; }}
#footer {{ height: 1; margin: 1 0; }}
#busy {{ width: 1fr; }}
#keys {{ width: auto; }}
#sidebar {{ width: 38; background: #111111; padding: 1 2; }}
#sidebar > Static {{ margin-bottom: 1; }}
#sidebar-spacer {{ height: 1fr; }}
PickerScreen, TextPromptScreen {{ align: center middle; background: #000000 60%; }}
#dialog {{ width: 70; height: auto; max-height: 90%; background: #161616; padding: 1 2; }}
#dialog-header {{ height: 1; margin-bottom: 1; }}
#dialog-title {{ width: 1fr; text-style: bold; }}
#dialog-esc {{ width: auto; color: #808080; }}
#dialog-body {{ margin-bottom: 1; max-height: 14; overflow-y: auto; }}
#dialog Input, #dialog Input:focus {{ border: none; background: #161616; padding: 0; height: 1; margin-bottom: 1; }}
#options {{ border: none; background: #161616; height: auto; max-height: 20; padding: 0; }}
#options:focus {{ border: none; }}
#options > .option-list--option-highlighted {{ background: {GOLD}; color: #000000; text-style: bold; }}
.hint {{ color: #808080; }}
"""


class PickerScreen(ModalScreen[str | None]):
    """Centered, searchable list; dismisses with the chosen Choice.value (None on esc)."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "close"),
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
    ]

    def __init__(
        self,
        title: str,
        choices: list[Choice],
        body: str = "",
        searchable: bool = True,
        selected: str | None = None,
    ) -> None:
        super().__init__()
        self._initial = selected
        self._title = title
        self._choices = choices
        self._body = body
        self._searchable = searchable

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            with Horizontal(id="dialog-header"):
                yield Static(Text(self._title), id="dialog-title")
                yield Static("esc", id="dialog-esc")
            if self._body:
                yield Static(Text(self._body), id="dialog-body")
            if self._searchable:
                yield Input(placeholder="Search", id="search")
            yield OptionList(id="options")

    def on_mount(self) -> None:
        self._show("")
        if not self._searchable:
            self.query_one(OptionList).focus()

    @on(Input.Changed, "#search")
    def _filter(self, event: Input.Changed) -> None:
        self._show(event.value)

    def _show(self, query: str) -> None:
        needle = query.strip().lower()
        options: list[Option] = []
        section = ""
        for choice in self._choices:
            if needle and needle not in f"{choice.label} {choice.hint}".lower():
                continue
            if choice.section != section:
                if options:  # blank line between sections
                    options.append(Option("", disabled=True))
                section = choice.section
                options.append(
                    Option(Text(section, style=f"bold {GOLD}"), disabled=True)
                )
            prompt = Text(choice.label)
            if choice.hint:
                prompt.append(f"  {choice.hint}", style="dim")
            options.append(Option(prompt, id=choice.value))

        option_list = self.query_one(OptionList)
        option_list.set_options(options)
        enabled = [i for i, option in enumerate(options) if not option.disabled]
        option_list.highlighted = next(
            (i for i in enabled if options[i].id == self._initial),
            enabled[0] if enabled else None,
        )

    def action_move(self, delta: int) -> None:
        option_list = self.query_one(OptionList)
        if delta > 0:
            option_list.action_cursor_down()
        else:
            option_list.action_cursor_up()

    @on(Input.Submitted, "#search")
    def _submit(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is not None:
            self.dismiss(option_list.get_option_at_index(option_list.highlighted).id)

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


class TextPromptScreen(ModalScreen[str | None]):
    """Centered single-line input; dismisses with the text (None on esc)."""

    BINDINGS = [Binding("escape", "dismiss(None)", "close")]

    def __init__(self, title: str, password: bool = False, default: str = "") -> None:
        super().__init__()
        self._title = title
        self._password = password
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            with Horizontal(id="dialog-header"):
                yield Static(Text(self._title), id="dialog-title")
                yield Static("esc", id="dialog-esc")
            yield Input(
                value=self._default, placeholder=self._title, password=self._password
            )
            yield Static("[b]enter[/] [dim]submit[/]", classes="hint")

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class SageApp(App[None]):
    CSS = CSS
    TITLE = "Sage"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+p", "commands", "commands"),
        Binding("escape", "interrupt", "interrupt"),
        Binding("ctrl+c", "quit", "quit", priority=True),
    ]

    orchestrator: AgentOrchestrator  # set by the caller right after construction

    def __init__(self, providers: ProviderRepository) -> None:
        super().__init__()
        self.providers = providers
        self._has_session = False
        self._session_title = "New session"
        self._context_tokens = 0
        self._session_tokens = 0
        self._busy_timer: Timer | None = None
        self._spin = 0

    # ---- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                with Vertical(id="composer"):
                    yield Input(
                        placeholder='Ask anything...  "Fix a TODO in the codebase"',
                        id="prompt",
                    )
                    yield Static(id="model-line")
                with Horizontal(id="footer"):
                    yield Static(id="busy")
                    yield Static("[b]ctrl+p[/] [dim]commands[/]", id="keys")
            with Vertical(id="sidebar"):
                yield Static(id="session-info")
                yield Static(id="context-info")
                yield Static(id="sidebar-spacer")
                yield Static(id="workspace-info")

    async def on_mount(self) -> None:
        await self._reset_log()
        self._refresh_status()
        self.query_one("#prompt", Input).focus()

    async def _reset_log(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.remove_children()
        await log.mount(Static(banner()), Static(_HELP, classes="meta"))

    def _refresh_status(self) -> None:
        llm = self.orchestrator.llm
        if llm is None:
            model = "[dim]no model connected — type[/] [b]/connect[/]"
            provider = "[dim]none[/]"
        else:
            active = llm.active_provider
            model = f"[b {GOLD}]Sage[/] · {active.model} [dim]{active.name}[/]"
            provider = f"{active.model}\n[dim]{active.name}[/]"
        self.query_one("#model-line", Static).update(model)
        self.query_one("#session-info", Static).update(
            Text(self._session_title, style="bold")
        )
        self.query_one("#context-info", Static).update(
            f"[b]Context[/]\n[dim]{self._context_tokens:,} tokens\n"
            f"{self._session_tokens:,} used this session[/]\n\n[b]Model[/]\n{provider}"
        )
        self.query_one("#workspace-info", Static).update(
            f"[dim]{self.orchestrator.sandbox.root}[/]\n\n"
            f"[{GOLD}]●[/] [b]Sage[/] [dim]{package_version('sage')}[/]"
        )

    def _set_busy(self, busy: bool) -> None:
        if self._busy_timer is not None:
            self._busy_timer.stop()
            self._busy_timer = None
        label = self.query_one("#busy", Static)
        if not busy:
            label.update("")
            return

        def spin() -> None:
            self._spin += 1
            frame = _SPINNER[self._spin % len(_SPINNER)]
            label.update(f"[{GOLD}]{frame}[/] [b]esc[/] [dim]interrupt[/]")

        spin()
        self._busy_timer = self.set_interval(0.1, spin)

    @property
    def busy(self) -> bool:
        return self._busy_timer is not None

    async def write(self, widget: Widget) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(widget)
        log.scroll_end(animate=False)

    async def note(self, message: str) -> None:
        await self.write(Static(Text(f"⚠ {message}"), classes="notice"))

    # ---- popups (call from a worker) ------------------------------------

    async def pick(
        self, title: str, choices: list[Choice], selected: str | None = None
    ) -> str | None:
        return await self.push_screen_wait(
            PickerScreen(title, choices, selected=selected)
        )

    async def ask(
        self, title: str, *, password: bool = False, default: str = ""
    ) -> str | None:
        return await self.push_screen_wait(TextPromptScreen(title, password, default))

    # ---- input ----------------------------------------------------------

    @on(Input.Submitted, "#prompt")
    def _submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if text.startswith("/") or text.lower() == "exit":
            self.run_command(text.lower())
        elif self.busy:
            self.notify("Still working — press esc to interrupt.")
        else:
            self.send(text)

    def action_commands(self) -> None:
        self.run_command_palette()

    @work(group="command")
    async def run_command_palette(self) -> None:
        command = await self.pick("Commands", COMMANDS)
        if command is not None:
            self.run_command(command)

    def action_interrupt(self) -> None:
        if self.busy:
            self.workers.cancel_group(self, "agent")
            self._set_busy(False)
            self.call_later(self.note, "Interrupted.")

    @work(exclusive=True, group="agent")
    async def send(self, text: str) -> None:
        if not self._has_session:
            await self.orchestrator.start_session(_title_from(text))
            self._has_session = True
            self._session_title = _title_from(text)
            self._session_tokens = 0
            self._refresh_status()

        await self.write(Static(Text(text), classes="user"))
        self._set_busy(True)
        try:
            outcome = await self.orchestrator.send_message(text)
        except Exception as exc:  # keep the app alive on any agent-loop failure
            await self.write(Static(Text(f"✗ {exc}"), classes="fail"))
            return
        finally:
            self._set_busy(False)
        if outcome is SessionOutcome.ENDED:
            self._has_session = False
            await self.note("Session saved. Your next message starts a new chat.")

    @work(group="command")
    async def run_command(self, command: str) -> None:
        if command in ("exit", "/exit", "/quit"):
            if self._has_session and not self.busy:
                await self.orchestrator.send_message("/exit")  # marks it completed
            self.exit()
        elif command == "/help":
            await self.write(Static(_HELP, classes="meta"))
        elif self.busy:
            self.notify("Still working — press esc to interrupt first.")
        elif command == "/new":
            self._has_session = False
            self._session_title = "New session"
            self._context_tokens = self._session_tokens = 0
            await self._reset_log()
            self._refresh_status()
        elif command == "/sessions":
            await self._resume()
        elif command == "/model":
            await self._switch_model()
        elif command == "/connect":
            await self._connect()
        else:
            await self.note(f"Unknown command {command}. Type /help.")

    # ---- commands -------------------------------------------------------

    async def _connect(self) -> None:
        credential = await connect_provider(
            self.pick, self.ask, self.providers, status=self.notify
        )
        if credential is None:
            await self.note("Connect cancelled.")
            return

        await self._activate(credential)
        await self.write(
            Static(f"✓ Connected {credential.name} · {credential.model}", classes="ok")
        )

    async def _activate(self, credential: ProviderCredential) -> None:
        """Make a (new or updated) credential the active provider."""
        llm = self.orchestrator.llm
        if llm is None:
            self.orchestrator.llm = LlmService(self.orchestrator.settings, [credential])
        else:
            await llm.add_provider(credential)
            await llm.switch_provider(
                next(p for p in llm.providers if p.name == credential.name)
            )
        self._refresh_status()

    async def _switch_model(self) -> None:
        """Pick any model from any connected provider, from their live /models lists."""
        llm = self.orchestrator.llm
        if llm is None:
            await self.note("No model connected yet. Type /connect.")
            return

        self.notify("Loading models...")
        catalogues = await asyncio.gather(
            *(list_models(p.api_key, p.endpoint) for p in llm.providers)
        )
        tags = {True: "free", False: "paid", None: ""}
        choices = []
        for provider, models in zip(llm.providers, catalogues, strict=True):
            known = KNOWN_PROVIDERS.get(provider.name)
            section = known.label if known else provider.name
            # Providers without a /models endpoint still offer their configured model.
            for model in models or [ModelInfo(provider.model)]:
                choices.append(
                    Choice(
                        model.id,
                        f"{provider.name}::{model.id}",
                        tags[model.free],
                        section,
                    )
                )

        active = llm.active_provider
        picked = await self.pick(
            "Switch model", choices, selected=f"{active.name}::{active.model}"
        )
        if picked is None:
            return
        name, _, model_id = picked.partition("::")
        provider = next(p for p in llm.providers if p.name == name)
        if provider == active and model_id == active.model:
            return

        credential = await self.providers.upsert(
            name, provider.api_key, model_id, provider.endpoint
        )
        await self._activate(credential)
        await self.write(
            Static(
                f"✓ Switched to {credential.model} · {credential.name}", classes="ok"
            )
        )

    async def _resume(self) -> None:
        sessions = await self.orchestrator.sessions.list()
        if not sessions:
            await self.note("No sessions yet.")
            return
        choices = [
            Choice(
                s.title,
                s.id,
                f"{'active' if s.status == 'active' else 'done'} · "
                f"{datetime.fromtimestamp(s.updated_at):%b %d %H:%M}",
            )
            for s in sessions
        ]
        session_id = await self.pick("Resume a chat", choices)
        if session_id is None:
            return

        session = await self.orchestrator.resume_session(session_id)
        self._has_session = True
        self._session_title = session.title
        self._context_tokens = self._session_tokens = 0
        await self._reset_log()
        await self._replay(self.orchestrator.history)
        self._refresh_status()

    async def _replay(self, history: list[Message]) -> None:
        """Show the tail of a resumed conversation so the user sees where they left off."""
        conversation = [m for m in history if m.role in ("user", "assistant")]
        shown = conversation[-_TRANSCRIPT_MESSAGES:]
        if omitted := len(conversation) - len(shown):
            await self.write(
                Static(f"... {omitted} earlier messages not shown ...", classes="meta")
            )
        for message in shown:
            if message.role == "user":
                await self.write(Static(Text(message.content), classes="user"))
            elif text := extract_text_part(message.content):
                await self.write(Markdown(text))

    # ---- agent output ---------------------------------------------------

    async def add_assistant(
        self, text: str, usage: TokenUsage, metrics: LlmMetrics
    ) -> None:
        if usage.total:
            self._context_tokens = usage.total
            self._session_tokens += usage.total
            self._refresh_status()
        await self.write(Markdown(text))
        meta = f"■ {metrics.model} · {metrics.total_duration_ms / 1000:.1f}s"
        if usage.total:
            meta += f" · ↑{usage.prompt_tokens:,} ↓{usage.completion_tokens:,}"
        await self.write(Static(meta, classes="meta"))


class TuiAgentUI:
    """AgentUI implementation that renders the agent loop into the SageApp."""

    def __init__(self, app: SageApp) -> None:
        self._app = app

    async def on_assistant_message(
        self, text: str, usage: TokenUsage, metrics: LlmMetrics
    ) -> None:
        await self._app.add_assistant(text, usage, metrics)

    async def on_command_panel(self, command: str) -> None:
        await self._app.write(Static(Text(f"$ {command}"), classes="tool"))

    async def on_tool_panel(self, kind: str, title: str) -> None:
        await self._app.write(Static(Text(f"{kind} · {title}"), classes="tool"))

    async def on_result(self, success: bool, summary: str) -> None:
        icon, style = ("✓", "ok") if success else ("✗", "fail")
        await self._app.write(Static(Text(f"{icon} {summary}"), classes=style))

    async def notify(self, message: str) -> None:
        await self._app.note(message)

    async def confirm(self, prompt: str, default: bool = True) -> bool:
        choices = [Choice("Yes", "yes"), Choice("No", "no")]
        if not default:
            choices.reverse()
        answer = await self._app.push_screen_wait(
            PickerScreen("Confirm", choices, body=prompt, searchable=False)
        )
        return answer == "yes"


def _title_from(first_message: str) -> str:
    title = " ".join(first_message.split())
    return title if len(title) <= 50 else title[:47] + "..."
