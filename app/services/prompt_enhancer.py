import json

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.sandbox import Sandbox
from app.services.doc_cache import DocCache

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/"
_TAVILY_ENDPOINT = "https://api.tavily.com/search"

_ENHANCER_SYSTEM_PROMPT = (
    "You are a concise prompt enhancer. You refine vague coding requests into clear, "
    "actionable specifications using the provided web search context. Be brief."
)

_ENHANCER_TEMPLATE = """You are a prompt enhancer for an autonomous coding agent.
Your job: transform vague user requests into detailed, actionable specifications.

Given the user's request, workspace context, and web search results, produce an enhanced version that includes:
1. **Tech stack** — infer from search results + workspace context, use current best practices
2. **Feature list** — explicit MVP features (only what was asked, nothing extra)
3. **File structure** — proposed directory layout
4. **Key dependencies** — specific package names and versions from search results
5. **Success criteria** — how to verify it works

Rules:
- If the request is ALREADY detailed (has specific tech, file paths, or code), return EXACTLY: PASS
- Keep enhancements concise — MAX 200 words
- Do NOT add features the user didn't ask for
- Prefer current, well-maintained libraries (use search results to verify)
- Output ONLY the enhanced specification, nothing else
- Do NOT include any preamble like "Here's the enhanced prompt:"

WORKSPACE CONTEXT:
{workspace_context}

WEB SEARCH RESULTS:
{search_results}

USER'S REQUEST:
{user_input}
"""

_META_COMMANDS = {"yes", "no", "ok", "y", "n", "continue", "approve", "reject", "skip"}
_PROJECT_EXTENSIONS = (".py", ".ts", ".js", ".html", ".json")
_IGNORED_WORKSPACE_ENTRIES = {
    "node_modules",
    "bin",
    "obj",
    "venv",
    ".venv",
    "__pycache__",
}


def is_already_detailed(user_input: str) -> bool:
    if not user_input.strip():
        return True
    if len(user_input) > 300 or "```" in user_input:
        return True
    if len(user_input.splitlines()) > 5:
        return True
    return "/" in user_input and any(ext in user_input for ext in _PROJECT_EXTENSIONS)


def is_meta_command(user_input: str) -> bool:
    trimmed = user_input.strip().lower()
    if trimmed.startswith("/") or trimmed.startswith("exit"):
        return True
    if trimmed in _META_COMMANDS:
        return True
    return len(user_input) < 15 and " " not in user_input


class PromptEnhancer:
    """Rewrites a vague first message into a detailed spec using Tavily search + Groq."""

    def __init__(
        self, settings: Settings, sandbox: Sandbox, doc_cache: DocCache
    ) -> None:
        self._sandbox = sandbox
        self._doc_cache = doc_cache
        self._tavily_api_key = settings.TAVILY_API_KEY
        self._http_client = httpx.AsyncClient(timeout=10.0)

        self._groq_client: AsyncOpenAI | None = None
        self._groq_model = settings.GROQ_MODEL
        if settings.GROQ_API_KEY:
            self._groq_client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY, base_url=_GROQ_ENDPOINT
            )

    async def enhance(self, user_input: str) -> tuple[str, bool]:
        """Return (possibly enhanced text, whether it was actually enhanced)."""
        if (
            self._groq_client is None
            or is_already_detailed(user_input)
            or is_meta_command(user_input)
        ):
            return user_input, False

        workspace_context = self._workspace_context()
        search_results = await self._tavily_search(user_input)
        prompt = _ENHANCER_TEMPLATE.format(
            workspace_context=workspace_context,
            search_results=search_results,
            user_input=user_input,
        )

        try:
            response = await self._groq_client.chat.completions.create(
                model=self._groq_model,
                messages=[
                    {"role": "system", "content": _ENHANCER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                timeout=15.0,
            )
        except Exception:
            return user_input, False

        content = (response.choices[0].message.content or "").strip()
        if not content or content.upper().startswith("PASS") or content == user_input:
            return user_input, False
        return content, True

    async def _tavily_search(self, query: str) -> str:
        if not self._tavily_api_key:
            return "(No web search — TAVILY_API_KEY not set)"

        cache_key = f"search:{query}"
        cached = await self._doc_cache.get("tavily", cache_key)
        if cached is not None:
            return cached

        try:
            response = await self._http_client.post(
                _TAVILY_ENDPOINT,
                json={
                    "api_key": self._tavily_api_key,
                    "query": f"best practices current libraries for: {query}",
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_answer": True,
                },
                timeout=8.0,
            )
        except httpx.TimeoutException:
            return "(Web search timed out)"

        if response.status_code != 200:
            return "(Web search failed)"

        result = _parse_tavily_response(response.text)
        await self._doc_cache.set("tavily", cache_key, result)
        return result

    def _workspace_context(self) -> str:
        root = self._sandbox.root
        parts = [f"Working directory: {root}"]

        markers = {
            "package.json": "Node.js",
            "pyproject.toml": "Python",
            "requirements.txt": "Python",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
        }
        for filename, project_type in markers.items():
            if (root / filename).exists():
                parts.append(f"Project type: {project_type}")

        entries = sorted(
            p.name
            for p in root.iterdir()
            if not p.name.startswith(".") and p.name not in _IGNORED_WORKSPACE_ENTRIES
        )[:15]
        parts.append(
            f"Root contents: {', '.join(entries)}"
            if entries
            else "Workspace is empty — new project"
        )
        return "\n".join(parts)


def _parse_tavily_response(raw_json: str) -> str:
    try:
        data = json.loads(raw_json)
    except ValueError:
        return "(Could not parse search results)"

    lines = []
    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip():
        lines.append(f"Summary: {answer}")

    for result in data.get("results", []):
        title = result.get("title")
        if title:
            content = (result.get("content") or "")[:200]
            lines.append(f"- {title}: {content}")

    return "\n".join(lines) if lines else "(No relevant results)"
