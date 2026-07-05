from rich.console import Console
from rich.prompt import Prompt

from app.models.provider import ProviderCredential
from app.repositories.provider_repository import ProviderRepository

GOLD = "#F0AA00"

_KNOWN_DEFAULTS = {
    "GROQ": ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/"),
    "ZHIPU": ("glm-4.7-flash", "https://open.bigmodel.cn/api/paas/v4/"),
}


async def connect_provider(
    console: Console, providers: ProviderRepository
) -> ProviderCredential | None:
    """Prompt for a provider name and API key, then persist the credential to the database."""
    name = (
        Prompt.ask("  Provider name (e.g. GROQ, ZHIPU, OPENAI)", console=console)
        .strip()
        .upper()
    )
    if not name:
        console.print("  [dim]Cancelled.[/]")
        return None

    api_key = Prompt.ask("  API key", password=True, console=console).strip()
    if not api_key:
        console.print("  [red]API key cannot be empty.[/]")
        return None

    default_model, default_endpoint = _KNOWN_DEFAULTS.get(name, ("", ""))
    model = (
        Prompt.ask("  Model", default=default_model, console=console).strip()
        or default_model
    )
    endpoint = (
        Prompt.ask(
            "  Endpoint (OpenAI-compatible base URL)",
            default=default_endpoint,
            console=console,
        ).strip()
        or default_endpoint
    )

    if not model or not endpoint:
        console.print(
            f"  [red]Model and endpoint are required for a provider not built in ({', '.join(_KNOWN_DEFAULTS)}).[/]"
        )
        return None

    credential = await providers.upsert(name, api_key, model, endpoint)
    console.print(
        f"  [{GOLD}]✓[/] Connected {credential.name} ({credential.model}) — saved locally."
    )
    return credential
