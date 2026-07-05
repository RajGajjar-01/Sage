from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from app.models.provider import ProviderCredential
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import list_models

GOLD = "#F0AA00"

_KNOWN_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "GROQ": ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/"),
    "ZHIPU": ("glm-4.7-flash", "https://open.bigmodel.cn/api/paas/v4/"),
    "CLOUDFLARE": ("@cf/meta/llama-3.1-8b-instruct", None),
}


async def connect_provider(
    console: Console, providers: ProviderRepository
) -> ProviderCredential | None:
    """Prompt for a provider name and API key, then persist the credential to the database."""
    name = (
        Prompt.ask(
            "  Provider name (e.g. GROQ, ZHIPU, CLOUDFLARE, OPENAI)", console=console
        )
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

    if name == "CLOUDFLARE" and default_endpoint is None:
        account_id = Prompt.ask("  Cloudflare Account ID", console=console).strip()
        if not account_id:
            console.print("  [red]Cloudflare Account ID is required.[/]")
            return None
        default_endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        )

    endpoint = (
        Prompt.ask(
            "  Endpoint (OpenAI-compatible base URL)",
            default=default_endpoint or "",
            console=console,
        ).strip()
        or default_endpoint
    )
    if not endpoint:
        console.print(
            f"  [red]An endpoint is required for a provider not built in ({', '.join(_KNOWN_DEFAULTS)}).[/]"
        )
        return None

    model = await _select_model(console, api_key, endpoint, default_model)
    if not model:
        console.print(
            f"  [red]A model is required for a provider not built in ({', '.join(_KNOWN_DEFAULTS)}).[/]"
        )
        return None

    credential = await providers.upsert(name, api_key, model, endpoint)
    console.print(
        f"  [{GOLD}]✓[/] Connected {credential.name} ({credential.model}) — saved locally."
    )
    return credential


async def _select_model(
    console: Console, api_key: str, endpoint: str, default_model: str
) -> str | None:
    """Let the user pick from the provider's live /models list, falling back to free text."""
    console.print("  [dim]Fetching available models...[/]")
    models = await list_models(api_key, endpoint)

    if not models:
        return (
            Prompt.ask("  Model", default=default_model, console=console).strip()
            or default_model
        )

    for i, model_id in enumerate(models, start=1):
        console.print(f"  {i}) {model_id}")
    pick = IntPrompt.ask("  Pick a model #", console=console)
    if 1 <= pick <= len(models):
        return models[pick - 1]

    console.print("  [red]Invalid choice.[/]")
    return None
