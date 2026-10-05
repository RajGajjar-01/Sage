from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.models.provider import ProviderCredential
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import ModelInfo, list_models


@dataclass(frozen=True)
class Choice:
    label: str
    value: str
    hint: str = ""
    section: str = ""


@dataclass(frozen=True)
class KnownProvider:
    label: str
    model: str  # "" = no sensible default, let the live /models list decide
    endpoint: str | None  # None = built by the flow (Cloudflare needs the account id)
    hint: str = ""


KNOWN_PROVIDERS: dict[str, KnownProvider] = {
    "OPENROUTER": KnownProvider(
        "OpenRouter", "", "https://openrouter.ai/api/v1", "free and paid models"
    ),
    "GROQ": KnownProvider(
        "Groq",
        "llama-3.3-70b-versatile",
        "https://api.groq.com/openai/v1/",
        "fast inference",
    ),
    "GEMINI": KnownProvider(
        "Google Gemini",
        "",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "OPENAI": KnownProvider("OpenAI", "", "https://api.openai.com/v1", "API key"),
    "CLOUDFLARE": KnownProvider(
        "Cloudflare Workers AI",
        "@cf/meta/llama-3.1-8b-instruct",
        None,
        "needs account ID",
    ),
    "ZHIPU": KnownProvider(
        "Zhipu GLM", "glm-4.7-flash", "https://open.bigmodel.cn/api/paas/v4/"
    ),
}
OTHER_PROVIDER = "__other__"

Pick = Callable[[str, list[Choice]], Awaitable[str | None]]


class Ask(Protocol):
    def __call__(
        self, title: str, *, password: bool = False, default: str = ""
    ) -> Awaitable[str | None]: ...


def provider_choices() -> list[Choice]:
    choices = [
        Choice(p.label, name, p.hint, "Popular") for name, p in KNOWN_PROVIDERS.items()
    ]
    choices.append(
        Choice("Other", OTHER_PROVIDER, "any OpenAI-compatible endpoint", "Custom")
    )
    return choices


def model_choices(models: list[ModelInfo]) -> list[Choice]:
    sections = {True: "Free", False: "Paid", None: "Models"}
    return [Choice(m.id, m.id, section=sections[m.free]) for m in models]


async def connect_provider(
    pick: Pick,
    ask: Ask,
    providers: ProviderRepository,
    status: Callable[[str], None] = lambda _: None,
) -> ProviderCredential | None:
    """Walk the user through provider -> API key -> model, then persist the credential.

    Returns None if the user cancels (or leaves a required answer empty) at any step."""
    name = await pick("Connect a provider", provider_choices())
    if name is None:
        return None

    known = KNOWN_PROVIDERS.get(name)
    if known is None:
        name = ((await ask("Provider name")) or "").strip().upper()
        endpoint: str | None = (
            (await ask("Endpoint (OpenAI-compatible base URL)")) or ""
        ).strip()
        if not name or not endpoint:
            return None
        label, default_model = name, ""
    else:
        label, endpoint, default_model = known.label, known.endpoint, known.model

    api_key = ((await ask(f"{label} API key", password=True)) or "").strip()
    if not api_key:
        return None

    if endpoint is None:
        account_id = ((await ask("Cloudflare account ID")) or "").strip()
        if not account_id:
            return None
        endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"

    status(f"Fetching {label} models...")
    models = await list_models(api_key, endpoint)
    if models:
        model = await pick(f"Select a {label} model", model_choices(models))
    else:
        model = ((await ask("Model", default=default_model)) or "").strip()
    if not model:
        return None

    return await providers.upsert(name, api_key, model, endpoint)
