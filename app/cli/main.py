import asyncio
from importlib.metadata import version as package_version

import typer
from rich.console import Console

from app.cli.tui import SageApp, TuiAgentUI
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
    typer.echo(f"sage {package_version('sage')}")


async def _run() -> None:
    console = Console()
    try:
        connection = await create_connection()
    except PermissionError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    try:
        sandbox = Sandbox(settings.WORKSPACE)
        provider_repo = ProviderRepository(connection)
        stored_credentials = await provider_repo.list()

        try:
            llm: LlmService | None = LlmService(settings, stored_credentials)
        except NoProviderConfiguredError:
            llm = None

        tui = SageApp(provider_repo)
        tui.orchestrator = AgentOrchestrator(
            sandbox=sandbox,
            llm=llm,
            shell=ShellExecutor(sandbox, settings.SHELL_TIMEOUT_SECONDS),
            file_tools=FileTools(sandbox),
            prompt_enhancer=PromptEnhancer(settings, sandbox, DocCache(connection)),
            sessions=SessionRepository(connection),
            messages=MessageRepository(connection),
            executions=ExecutionRepository(connection),
            ui=TuiAgentUI(tui),
            settings=settings,
        )

        await tui.run_async()
    finally:
        await connection.close()


if __name__ == "__main__":
    app()
