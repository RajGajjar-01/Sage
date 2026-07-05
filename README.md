# DotAgent

DotAgent is an autonomous coding agent, rewritten in Python from the original .NET/Spectre.Console prototype. It runs as a CLI you install locally, backed by a sandboxed workspace and a FastAPI service layer.

## Features

- Plan Mode and Execute Mode workflow with mandatory user approval between them.
- Workspace sandbox: every file and shell operation is restricted to a single configured directory.
- Multi-provider LLM support (Groq, ZhipuAI) with automatic fallback on rate limits or errors.
- Resumable sessions backed by SQLite.
- A versioned FastAPI surface (`/api/v1`) alongside the CLI for programmatic access.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Getting started

```bash
uv sync
cp .env.example .env   # fill in provider keys
uv run dotagent
```

## Project layout

- `app/core/` — settings, sandbox enforcement, database wiring, response envelope.
- `app/models/` — persistence-layer dataclasses.
- `app/repositories/` — SQLite data access.
- `app/services/` — LLM service, shell executor, file tools, orchestrator, prompt enhancer.
- `app/api/v1/` — FastAPI routers.
- `app/cli/` — the CLI front end.
