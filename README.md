# Sage

Sage is an autonomous coding agent, rewritten in Python from the original .NET/Spectre.Console prototype. It's a CLI you install locally: it explores a codebase, writes a plan, waits for your approval, then executes it step by step inside a sandboxed workspace. A FastAPI service exposing the same session/provider data lives alongside it.

## Features

- Plan Mode and Execute Mode workflow, with mandatory user approval before execution.
- Workspace sandbox: every file and shell operation is confined to a single configured directory, enforced at the point of execution (not just as a pre-check).
- Multi-provider LLM support with automatic round-robin fallback on rate limits or errors. Any OpenAI-compatible endpoint works; `/connect` knows the defaults for Groq, ZhipuAI, Cloudflare Workers AI, OpenRouter, Gemini and OpenAI, and lets you filter long model catalogues (OpenRouter lists 400+).
- Resumable sessions backed by SQLite.
- A Tavily-backed prompt enhancer that expands vague first messages into a detailed spec.
- A versioned FastAPI surface (`/api/v1`) for session/provider access alongside the CLI.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Getting started

```bash
uv sync
uv run sage
```

No `.env` required to get started: Sage boots straight into the menu even with zero providers configured. Type `/connect` at the chat prompt anytime to add or update a provider (saved to the local SQLite database, no restart needed) — if you send a message before connecting one, Sage just tells you to run `/connect` first. `TAVILY_API_KEY` is optional and only powers the prompt enhancer.

## Running the API

```bash
uv run uvicorn app.main:app --reload
```

Endpoints live under `/api/v1` (`/sessions`, `/providers`, `/providers/connect`), plus `/live` and `/health`.

## Docker

```bash
docker compose up cli    # interactive CLI, same as `uv run sage`
docker compose up api    # FastAPI server on :8000
```

Both share the same image; `./workspace` and `./data` are mounted so the sandbox and SQLite database persist across runs.

## Project layout

- `app/core/` — settings (pydantic-settings, no python-dotenv), the workspace sandbox, database wiring, response envelope, exception handlers.
- `app/models/` — persistence-layer dataclasses (`Session`, `Message`, `Execution`, `ProviderCredential`).
- `app/repositories/` — SQLite data access, one repository per model.
- `app/services/` — `LlmService` (multi-provider), `ShellExecutor`, `FileTools`, `ActionParser`, `AgentOrchestrator`, `PromptEnhancer`, `DocCache`.
- `app/api/v1/` — FastAPI routers.
- `app/cli/` — the CLI front end (banner, menu, `/connect`, Rich-based `AgentUI` implementation).

## Development

```bash
uv run pytest
uv run ruff format . && uv run ruff check .
uv run mypy app
```
