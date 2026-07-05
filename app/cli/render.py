from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule

from app.services.llm_service import LlmMetrics, TokenUsage

GOLD = "#F0AA00"


class RichConsoleUI:
    """AgentUI implementation that renders the agent loop through Rich."""

    def __init__(self, console: Console) -> None:
        self._console = console

    async def on_assistant_message(
        self, text: str, usage: TokenUsage, metrics: LlmMetrics
    ) -> None:
        self._console.print(Rule("[bold]Agent[/]", style=f"{GOLD} dim"))
        if usage.total:
            info = f"tokens: ↑ {usage.prompt_tokens:,} ↓ {usage.completion_tokens:,} Σ {usage.total:,}"
            info += f"  │  TTFT: {metrics.time_to_first_token_ms:.0f}ms  Total: {metrics.total_duration_ms:.0f}ms"
            self._console.print(info, style="dim", justify="right")
        self._console.print(Markdown(text))
        self._console.print(Rule(style="dim"))

    async def on_command_panel(self, command: str) -> None:
        self._console.print(
            Panel(command, title="bash", border_style=GOLD, padding=(1, 1))
        )

    async def on_tool_panel(self, kind: str, title: str) -> None:
        self._console.print(Panel(title, title=kind, border_style=GOLD, padding=(1, 1)))

    async def on_result(self, success: bool, summary: str) -> None:
        icon, color = ("✓", "green") if success else ("✗", "red")
        self._console.print(f"  [{color}]{icon}[/] [dim]{summary}[/]")

    async def notify(self, message: str) -> None:
        self._console.print(f"  [{GOLD}]⚠[/] [dim]{message}[/]")

    async def confirm(self, prompt: str, default: bool = True) -> bool:
        return Confirm.ask(
            f"  [{GOLD}]{prompt}[/]", default=default, console=self._console
        )
