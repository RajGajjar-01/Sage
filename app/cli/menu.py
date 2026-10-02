from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from app.cli.banner import print_banner
from app.cli.connect import connect_provider, pick_number
from app.models.agent import Message
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import LlmService
from app.services.orchestrator import (
    AgentOrchestrator,
    SessionOutcome,
    extract_text_part,
)

GOLD = "#F0AA00"
_TRANSCRIPT_MESSAGES = 10


async def run_menu(
    orchestrator: AgentOrchestrator, console: Console, providers: ProviderRepository
) -> None:
    print_banner(console)

    while True:
        model_label = (
            orchestrator.llm.active_provider.model
            if orchestrator.llm
            else "no model connected"
        )
        console.print(
            f"  [bold {GOLD}]What do you want to do?[/]  [dim]({model_label})[/]"
        )
        console.print("  1) New chat")
        console.print("  2) Load session")
        console.print("  3) Switch model")
        console.print("  4) Exit")
        console.print("  [dim](type /connect anytime to add or update a provider)[/]")
        choice = Prompt.ask(
            "  Choice",
            choices=["1", "2", "3", "4"],
            default="1",
            console=console,
            show_choices=False,
        )
        console.print()

        if choice == "1":
            await _new_chat(orchestrator, console, providers)
        elif choice == "2":
            await _load_session(orchestrator, console, providers)
        elif choice == "3":
            await _switch_model(orchestrator, console)
        else:
            console.print("  [dim]Goodbye.[/]")
            return
        console.print()


async def _new_chat(
    orchestrator: AgentOrchestrator, console: Console, providers: ProviderRepository
) -> None:
    title = Prompt.ask(
        "  Session title (or press Enter)", default="", console=console
    ).strip()
    if not title:
        title = f"Session {datetime.now():%b %d %H:%M}"

    session = await orchestrator.start_session(title)
    console.print(
        f"  [dim]Session started:[/] [{GOLD}]{session.id[:8]}[/] · {session.title}"
    )
    console.print()
    await _chat_loop(orchestrator, console, providers)


async def _load_session(
    orchestrator: AgentOrchestrator, console: Console, providers: ProviderRepository
) -> None:
    sessions = await orchestrator.sessions.list()
    if not sessions:
        console.print("  [dim]No sessions yet. Start a new chat first.[/]")
        return

    table = Table(border_style="grey50")
    table.add_column("#", justify="center")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Last active")
    for i, session in enumerate(sessions, start=1):
        last_active = datetime.fromtimestamp(session.updated_at).strftime("%b %d %H:%M")
        status = (
            "[green]● active[/]" if session.status == "active" else "[dim]○ done[/]"
        )
        table.add_row(
            f"[{GOLD}]{i}[/]", session.id[:8], session.title, status, last_active
        )
    console.print(table)

    pick = pick_number(console, "  Pick a session # (0 to cancel)", len(sessions))
    if pick == 0:
        return

    session = await orchestrator.resume_session(sessions[pick - 1].id)
    console.print(f"  [dim]Resuming:[/] [{GOLD}]{session.id[:8]}[/] · {session.title}")
    console.print()
    _print_transcript(console, orchestrator.history)
    await _chat_loop(orchestrator, console, providers)


async def _chat_loop(
    orchestrator: AgentOrchestrator, console: Console, providers: ProviderRepository
) -> None:
    while True:
        user_input = Prompt.ask(f"  [bold {GOLD}]You ›[/]", console=console).strip()
        if not user_input:
            continue

        if user_input.lower() == "/connect":
            credential = await connect_provider(console, providers)
            if credential is not None:
                if orchestrator.llm is None:
                    orchestrator.llm = LlmService(orchestrator.settings, [credential])
                else:
                    await orchestrator.llm.add_provider(credential)
            console.print()
            continue

        try:
            outcome = await orchestrator.send_message(user_input)
        except Exception as exc:  # keep the session alive on any agent-loop failure
            console.print(f"  [red]Error:[/] {exc}")
            continue
        if outcome is SessionOutcome.ENDED:
            console.print("  [dim]Session saved. Returning to menu.[/]")
            return


async def _switch_model(orchestrator: AgentOrchestrator, console: Console) -> None:
    llm = orchestrator.llm
    if llm is None:
        console.print(
            "  [dim]No model connected yet. Start a chat and type /connect.[/]"
        )
        return
    if len(llm.providers) <= 1:
        console.print(
            "  [dim]Only one provider configured. Add more in your .env file.[/]"
        )
        return

    for i, provider in enumerate(llm.providers, start=1):
        marker = " ●" if provider.name == llm.active_provider.name else ""
        console.print(f"  {i}) {provider.name} · {provider.model}{marker}")

    pick = pick_number(console, "  Pick a model # (0 to cancel)", len(llm.providers))
    if pick == 0:
        return
    await llm.switch_provider(llm.providers[pick - 1])
    console.print(
        f"  [{GOLD}]Switched to[/] {llm.active_provider.model} ({llm.active_provider.name})"
    )


def _print_transcript(console: Console, history: list[Message]) -> None:
    """Replay the tail of a resumed conversation so the user can see where they left off."""
    conversation = [m for m in history if m.role in ("user", "assistant")]
    shown = conversation[-_TRANSCRIPT_MESSAGES:]
    if not shown:
        return

    omitted = len(conversation) - len(shown)
    if omitted > 0:
        console.print(f"  [dim]... {omitted} earlier messages not shown ...[/]")
    for message in shown:
        if message.role == "user":
            console.print(f"  [bold {GOLD}]You ›[/] {message.content}")
        elif text := extract_text_part(message.content):
            console.print(Markdown(text))
    console.print(Rule(style="dim"))
    console.print()
