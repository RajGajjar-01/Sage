from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import OptionList

from app.cli.tui import PickerScreen, SageApp, TextPromptScreen
from app.services.llm_service import ModelInfo


def _app() -> SageApp:
    providers = SimpleNamespace(
        upsert=AsyncMock(
            side_effect=lambda name, key, model, endpoint: SimpleNamespace(
                name=name, api_key=key, model=model, endpoint=endpoint
            )
        )
    )
    app = SageApp(providers)  # type: ignore[arg-type]
    app.orchestrator = SimpleNamespace(  # type: ignore[assignment]
        llm=None, sandbox=SimpleNamespace(root=Path("/tmp/ws")), settings=None
    )
    return app


def _options(app: SageApp) -> list[str]:
    option_list = app.screen.query_one(OptionList)
    return [
        str(option_list.get_option_at_index(i).id)
        for i in range(option_list.option_count)
        if not option_list.get_option_at_index(i).disabled
    ]


@pytest.mark.asyncio
async def test_connect_flow_through_popups():
    app = _app()
    models = [ModelInfo("free-model", True), ModelInfo("paid-model", False)]
    with (
        patch("app.cli.connect.list_models", AsyncMock(return_value=models)),
        patch("app.cli.tui.LlmService") as llm_service,
    ):
        async with app.run_test() as pilot:
            await pilot.press(*"/connect", "enter")
            await pilot.pause()
            assert isinstance(app.screen, PickerScreen)

            await pilot.press(*"router")  # search narrows the provider list
            assert _options(app) == ["OPENROUTER"]
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, TextPromptScreen)
            await pilot.press(*"sk-test", "enter")
            await pilot.pause()

            assert isinstance(app.screen, PickerScreen)
            assert _options(app) == ["free-model", "paid-model"]
            await pilot.press("down", "enter")
            await pilot.pause()

            assert not isinstance(app.screen, PickerScreen | TextPromptScreen)

    app.providers.upsert.assert_awaited_once_with(  # type: ignore[attr-defined]
        "OPENROUTER", "sk-test", "paid-model", "https://openrouter.ai/api/v1"
    )
    llm_service.assert_called_once()


@pytest.mark.asyncio
async def test_escape_closes_the_command_palette():
    app = _app()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, PickerScreen)


@pytest.mark.asyncio
async def test_model_picker_lists_every_providers_models_and_switches():
    from app.core.config import Settings
    from app.models.provider import ProviderCredential
    from app.services.llm_service import LlmService

    app = _app()
    llm = LlmService(
        Settings(GROQ_API_KEY=None, ZHIPU_API_KEY=None),
        [
            ProviderCredential("GROQ", "gk", "llama-a", "https://groq.example/v1"),
            ProviderCredential("OPENROUTER", "ok", "x/free", "https://or.example/v1"),
        ],
    )
    app.orchestrator.llm = llm
    catalogues = {
        "gk": [ModelInfo("llama-a"), ModelInfo("llama-b")],
        "ok": [ModelInfo("x/free", True), ModelInfo("y/paid", False)],
    }

    async def fake_list_models(api_key, endpoint):
        return catalogues[api_key]

    with patch("app.cli.tui.list_models", fake_list_models):
        async with app.run_test() as pilot:
            await pilot.press(*"/model", "enter")
            await pilot.pause()
            assert isinstance(app.screen, PickerScreen)
            assert _options(app) == [
                "GROQ::llama-a",
                "GROQ::llama-b",
                "OPENROUTER::x/free",
                "OPENROUTER::y/paid",
            ]
            await pilot.press(*"paid")  # search spans all providers
            assert _options(app) == ["OPENROUTER::y/paid"]
            await pilot.press("enter")
            await pilot.pause()

    assert llm.active_provider.name == "OPENROUTER"
    assert llm.active_provider.model == "y/paid"
    app.providers.upsert.assert_awaited_once_with(  # type: ignore[attr-defined]
        "OPENROUTER", "ok", "y/paid", "https://or.example/v1"
    )
