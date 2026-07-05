import asyncio

import typer
from rich.console import Console

from app.cli.menu import run_menu
from app.cli.render import RichConsoleUI
from app.core.config import settings
from app.core.database import create_connection
from app.core.sandbox import Sandbox
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.session_repository import SessionRepository
from app.services.doc_cache import DocCache
from app.services.file_tools import FileTools
from app.services.llm_service import LlmService, NoProviderConfiguredError
from app.services.orchestrator import AgentOrchestrator
from app.services.prompt_enhancer import PromptEnhancer
from app.services.shell_executor import ShellExecutor

app = typer.Typer(
    name="sage",
    help="Autonomous coding agent with a sandboxed workspace.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the interactive Sage session."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_run())


@app.command()
def version() -> None:
    """Print the installed sage version."""
    typer.echo("sage 0.1.0")


async def _run() -> None:
    console = Console()
    connection = await create_connection()

    try:
        sandbox = Sandbox(settings.WORKSPACE)
        provider_repo = ProviderRepository(connection)
        stored_credentials = await provider_repo.list()

        try:
            llm: LlmService | None = LlmService(settings, stored_credentials)
        except NoProviderConfiguredError:
            llm = None

        orchestrator = AgentOrchestrator(
            sandbox=sandbox,
            llm=llm,
            shell=ShellExecutor(sandbox, settings.SHELL_TIMEOUT_SECONDS),
            file_tools=FileTools(sandbox),
            prompt_enhancer=PromptEnhancer(settings, sandbox, DocCache(connection)),
            sessions=SessionRepository(connection),
            messages=MessageRepository(connection),
            executions=ExecutionRepository(connection),
            ui=RichConsoleUI(console),
            settings=settings,
        )

        try:
            await run_menu(orchestrator, console, provider_repo)
        except (KeyboardInterrupt, EOFError):
            console.print("\n  [dim]Interrupted.[/]")
    finally:
        await connection.close()


if __name__ == "__main__":
    app()
