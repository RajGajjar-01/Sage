import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import Settings
from app.models.agent import Message
from app.models.provider import ProviderCredential

_RATE_LIMIT_MARKERS = (
    "rate limit",
    "quota",
    "exceeded",
    "429",
    "insufficient",
    "billing",
    "credits",
    "unauthorized",
    "invalid api key",
    "api key",
)


class NoProviderConfiguredError(Exception):
    """Raised when no LLM provider has an API key set."""


class ProvidersExhaustedError(Exception):
    """Raised when every configured provider failed for a single completion request."""


@dataclass(frozen=True)
class LlmProvider:
    name: str
    api_key: str
    model: str
    endpoint: str


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int | None = None

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class LlmMetrics:
    provider: str
    model: str
    time_to_first_token_ms: float
    total_duration_ms: float
    usage: TokenUsage


def load_providers(
    settings: Settings, stored: list[ProviderCredential] | None = None
) -> list[LlmProvider]:
    """Build the ordered provider list: env-configured first (Groq tried first),
    then DB-stored credentials from /connect, which override same-named entries
    in place rather than reordering them."""
    providers: dict[str, LlmProvider] = {}
    if settings.GROQ_API_KEY:
        providers["GROQ"] = LlmProvider(
            "GROQ", settings.GROQ_API_KEY, settings.GROQ_MODEL, settings.GROQ_ENDPOINT
        )
    if settings.ZHIPU_API_KEY:
        providers["ZHIPU"] = LlmProvider(
            "ZHIPU",
            settings.ZHIPU_API_KEY,
            settings.ZHIPU_MODEL,
            settings.ZHIPU_ENDPOINT,
        )
    for credential in stored or []:
        providers[credential.name] = LlmProvider(
            credential.name, credential.api_key, credential.model, credential.endpoint
        )
    return list(providers.values())


def is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)


async def list_models(
    api_key: str, endpoint: str, timeout_seconds: float = 10.0
) -> list[str]:
    """Best-effort fetch of available model IDs from an OpenAI-compatible /models endpoint.

    Returns an empty list if the provider doesn't implement it or the request fails --
    callers should fall back to letting the user type a model name by hand."""
    client = AsyncOpenAI(api_key=api_key, base_url=endpoint, timeout=timeout_seconds)
    try:
        response = await client.models.list()
        return sorted(model.id for model in response.data)
    except Exception:
        return []
    finally:
        await client.close()


class LlmService:
    """OpenAI-compatible chat completions client with multi-provider fallback."""

    def __init__(
        self,
        settings: Settings,
        stored_credentials: list[ProviderCredential] | None = None,
    ) -> None:
        self._settings = settings
        self._providers = load_providers(settings, stored_credentials)
        if not self._providers:
            raise NoProviderConfiguredError(
                "No LLM providers configured. Set GROQ_API_KEY/ZHIPU_API_KEY or run /connect."
            )
        self._provider_index = 0
        self._client = self._build_client(self.active_provider)

    @property
    def providers(self) -> list[LlmProvider]:
        return self._providers

    @property
    def active_provider(self) -> LlmProvider:
        return self._providers[self._provider_index]

    async def switch_provider(self, provider: LlmProvider) -> None:
        old_client = self._client
        self._provider_index = self._providers.index(provider)
        self._client = self._build_client(provider)
        await old_client.close()

    async def switch_to_next_provider(self) -> bool:
        """Round-robin to the next provider. Returns False once it has cycled back."""
        next_index = (self._provider_index + 1) % len(self._providers)
        if next_index == self._provider_index:
            return False
        old_client = self._client
        self._provider_index = next_index
        self._client = self._build_client(self.active_provider)
        await old_client.close()
        return True

    async def add_provider(self, credential: ProviderCredential) -> None:
        """Add or update a provider from a stored credential, usable without restarting."""
        new_provider = LlmProvider(
            credential.name, credential.api_key, credential.model, credential.endpoint
        )
        existing_index = next(
            (i for i, p in enumerate(self._providers) if p.name == credential.name),
            None,
        )

        if existing_index is not None:
            self._providers[existing_index] = new_provider
            if existing_index == self._provider_index:
                old_client = self._client
                self._client = self._build_client(new_provider)
                await old_client.close()
            return

        self._providers.append(new_provider)
        if len(self._providers) == 1:
            self._provider_index = 0
            self._client = self._build_client(new_provider)

    def _build_client(self, provider: LlmProvider) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=provider.api_key,
            base_url=provider.endpoint,
            timeout=self._settings.LLM_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _to_chat_message(message: Message) -> dict[str, Any]:
        role = "user" if message.role == "tool_result" else message.role
        return {"role": role, "content": message.content}

    async def complete(
        self,
        history: list[Message],
        system_prompt: str,
        on_token: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str, TokenUsage, LlmMetrics]:
        """Stream a chat completion, falling back to the next provider on rate-limit errors."""
        chat_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        chat_messages.extend(self._to_chat_message(m) for m in history)

        attempts = 0
        last_error: Exception | None = None

        while attempts < len(self._providers):
            attempts += 1
            provider = self.active_provider
            full_response: list[str] = []
            usage = TokenUsage()
            first_token_ms = 0.0
            first_token_seen = False
            started = time.perf_counter()

            try:
                stream = await self._client.chat.completions.create(
                    model=provider.model,
                    messages=cast(list[ChatCompletionMessageParam], chat_messages),
                    stream=True,
                    stream_options={"include_usage": True},
                )
                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            if not first_token_seen:
                                first_token_ms = (time.perf_counter() - started) * 1000
                                first_token_seen = True
                            full_response.append(delta)
                            if on_token is not None:
                                await on_token(delta)
                    if chunk.usage is not None:
                        usage = TokenUsage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                        )

                total_ms = (time.perf_counter() - started) * 1000
                metrics = LlmMetrics(
                    provider.name, provider.model, first_token_ms, total_ms, usage
                )
                return "".join(full_response), usage, metrics

            except Exception as exc:
                last_error = exc
                if is_rate_limit_error(exc) and await self.switch_to_next_provider():
                    continue
                raise ProvidersExhaustedError(
                    f"All providers exhausted: {exc}"
                ) from exc

        raise ProvidersExhaustedError(
            f"All providers exhausted after {attempts} attempts: {last_error}"
        )
