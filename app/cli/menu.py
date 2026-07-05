from datetime import datetime

from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from app.cli.banner import print_banner
from app.cli.connect import connect_provider
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import LlmService
from app.services.orchestrator import AgentOrchestrator, SessionOutcome

GOLD = "#F0AA00"


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

    pick = IntPrompt.ask("  Pick a session # (0 to cancel)", console=console)
    if pick == 0 or pick > len(sessions):
        return

    session = await orchestrator.resume_session(sessions[pick - 1].id)
    console.print(f"  [dim]Resuming:[/] [{GOLD}]{session.id[:8]}[/] · {session.title}")
    console.print()
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

        outcome = await orchestrator.send_message(user_input)
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

    pick = IntPrompt.ask("  Pick a model #", console=console)
    if 1 <= pick <= len(llm.providers):
        await llm.switch_provider(llm.providers[pick - 1])
        console.print(
            f"  [{GOLD}]Switched to[/] {llm.active_provider.model} ({llm.active_provider.name})"
        )
