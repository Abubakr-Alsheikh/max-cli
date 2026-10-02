"""The AI page: the agent in the dashboard, with a scripted model (no network)."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from textual.widgets import Button, Input, Static

from max_cli.common.exceptions import AIError
from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.widgets.ai_panel import AIPanel
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

from .waiting import wait_until

SIZE = (140, 44)
CLIENT_PATH = "max_cli.core.engines.ai_engine.make_client"


def _call(name: str, arguments: dict, call_id: str) -> Any:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _answer(content: str = "", calls: tuple = ()) -> Any:
    message = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=100),
    )


class ScriptedModel:
    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        answer = self._responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _run(action: str, arguments: dict) -> tuple:
    group = action.split(".")[0]
    return (
        _answer(calls=(_call("load_group", {"name": group}, "call-1"),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": action, "arguments": arguments},
                    "call-2",
                ),
            )
        ),
    )


@pytest.fixture
def ai_on(monkeypatch, tmp_path):
    """An API key is set, and the agent starts in tmp_path."""
    from max_cli.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _texts(app: MaxDashboardApp, selector: str) -> list[str]:
    return [str(line.content) for line in app.query(selector).results(Static)]


async def _send(app: MaxDashboardApp, pilot, request: str) -> None:
    app.navigate("ai")
    await pilot.pause()
    app.query_one("#ai-input", Input).value = request
    app.query_one("#ai-send", Button).press()


async def _replied(app: MaxDashboardApp, pilot) -> None:
    panel = app.query_one(AIPanel)
    await wait_until(pilot, lambda: not panel._busy and bool(app.query(".ai-reply")))


# --- the page ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_ai_the_page_points_to_settings(monkeypatch):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press(SECTION_KEYS["ai"])
        await pilot.pause()
        assert app.query_one("#ai-setup").has_class("-shown")

        app.query_one("#ai-open-settings", Button).press()
        await wait_until(pilot, lambda: app.query_one("#settings-panel").display)


@pytest.mark.asyncio
async def test_a_saved_chat_page_opens_ai():
    from max_cli.interface.tui.ui_prefs import save_pref

    save_pref("last_page", "chat")
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app.query_one("#ai-panel").display


# --- a request ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_request_shows_its_steps_and_the_reply(ai_on):
    (ai_on / "note.txt").write_text("hello", encoding="utf-8")
    model = ScriptedModel(
        *_run("files.preview", {"target": "note.txt"}), _answer("It says hello.")
    )
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "what's in note.txt?")
            await _replied(app, pilot)
            steps = _texts(app, ".ai-step")
            replies = _texts(app, ".ai-reply")
            status = str(app.query_one("#ai-status", Static).content)

    assert any("Looked up the files actions" in step for step in steps)
    assert any(step.startswith("✓") for step in steps)
    assert not any("Thinking" in step for step in steps)
    assert replies == ["Max  It says hello."]
    assert "300 tokens" in status
    categories = {
        (entry.category, entry.action) for entry in ActivityLog().get_entries()
    }
    assert {("ai", "agent"), ("files", "preview")} <= categories


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, kept", [("#confirm-no", True), ("#confirm-yes", False)]
)
async def test_a_delete_asks_first(ai_on, answer, kept):
    note = ai_on / "note.txt"
    note.write_text("secret", encoding="utf-8")
    model = ScriptedModel(*_run("files.shred", {"target": "note.txt"}), _answer("OK."))
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "shred note.txt")
            await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))
            assert "files shred" in str(
                app.screen.query_one("#confirm-question", Static).content
            )
            app.screen.query_one(answer, Button).press()
            await _replied(app, pilot)

    assert note.exists() is kept


@pytest.mark.asyncio
async def test_a_file_change_offers_undo(ai_on):
    (ai_on / "a.txt").write_text("a", encoding="utf-8")
    model = ScriptedModel(
        *_run("files.order", {"folder": str(ai_on)}), _answer("Numbered them.")
    )
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "number the files here")
            await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))
            app.screen.query_one("#confirm-yes", Button).press()
            await _replied(app, pilot)
            await wait_until(pilot, lambda: bool(app.query(".ai-undo")))

            app.query_one(".ai-undo", Button).press()
            await wait_until(pilot, lambda: app.query_one("#activity-panel").display)

    assert (ai_on / "1_a.txt").exists()


@pytest.mark.asyncio
async def test_an_ai_error_is_shown_and_the_page_recovers(ai_on):
    model = ScriptedModel(AIError("The AI didn't answer: timed out"), _answer("Hi."))
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "hello")
            await _replied(app, pilot)
            assert "timed out" in _texts(app, ".ai-reply")[-1]

            app.query_one("#ai-input", Input).value = "again"
            app.query_one("#ai-send", Button).press()
            await wait_until(pilot, lambda: len(app.query(".ai-reply")) == 2)
            assert _texts(app, ".ai-reply")[-1] == "Max  Hi."


@pytest.mark.asyncio
async def test_an_example_sends_and_new_chat_starts_over(ai_on):
    model = ScriptedModel(_answer("Nothing to shrink here."))
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            app.navigate("ai")
            await pilot.pause()
            app.query_one("#ai-example-0", Button).press()
            await _replied(app, pilot)
            panel = app.query_one(AIPanel)
            assert not app.query_one("#ai-examples").display
            assert panel._agent is not None

            app.query_one("#ai-new", Button).press()
            await pilot.pause()

            assert panel._agent is None
            assert not app.query(".ai-reply")
            assert app.query_one("#ai-examples").display
