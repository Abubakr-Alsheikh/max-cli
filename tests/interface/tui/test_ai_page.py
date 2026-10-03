"""The AI page: the agent in the dashboard, with a scripted model (no network)."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from textual.widgets import Button, Input, Markdown, Static

from max_cli.common.activity_log import ActivityLog
from max_cli.common.exceptions import AIError
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.widgets.ai_panel import AgentTurn, AIPanel, ToolCard
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

from .waiting import wait_until

SIZE = (140, 44)
CLIENT_PATH = "max_cli.core.engines.ai_providers.make_client"


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


def _replies(app: MaxDashboardApp) -> list[str]:
    """Each finished turn's answer: its Markdown source, or its error."""
    answers = []
    for turn in app.query(AgentTurn):
        # A Markdown widget's source is empty until its own mount runs.
        answers += [
            markdown.source for markdown in turn.query(Markdown) if markdown.source
        ]
        for error in turn.query(".turn-error").results(Static):
            answers.append(str(error.content))
    return answers


async def _send(app: MaxDashboardApp, pilot, request: str) -> None:
    app.navigate("ai")
    await pilot.pause()
    app.query_one("#ai-input", Input).value = request
    app.query_one("#ai-send", Button).press()


async def _replied(app: MaxDashboardApp, pilot, count: int = 1) -> None:
    panel = app.query_one(AIPanel)
    await wait_until(pilot, lambda: not panel._busy and len(_replies(app)) >= count)


async def _dialog_open(app: MaxDashboardApp, pilot) -> None:
    """The question is on screen with its buttons: the screen switches a
    moment before they mount."""
    await wait_until(
        pilot,
        lambda: isinstance(app.screen, ConfirmDialog)
        and bool(app.screen.query("#confirm-yes")),
    )


# --- the page ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_ai_the_page_points_to_settings(monkeypatch):
    from max_cli.config import settings

    # Pin every provider setting: the real settings file may set one up.
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "")
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
        *_run("files.preview", {"target": "note.txt"}),
        _answer("It says **hello**.\n\n- one\n- two"),
    )
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "what's in note.txt?")
            await _replied(app, pilot)
            [card] = app.query(ToolCard)
            lookups = str(app.query_one(".turn-lookups", Static).content)
            turn_status = str(app.query_one(".turn-status", Static).content)
            status = str(app.query_one("#ai-status", Static).content)
            replies = _replies(app)

    assert card.has_class("-ok")
    assert card.title.startswith("✓ files preview")
    assert "files actions" in lookups
    assert "1 action" in turn_status and "300 tokens" in turn_status
    assert replies == ["It says **hello**.\n\n- one\n- two"]
    assert "300 tokens" in status
    categories = {
        (entry.category, entry.action) for entry in ActivityLog().get_entries()
    }
    assert {("ai", "agent"), ("files", "preview")} <= categories


@pytest.mark.asyncio
async def test_actions_run_side_by_side_each_get_their_card(ai_on):
    for name in ("a", "b"):
        (ai_on / name).mkdir()
        (ai_on / name / "note.txt").write_text(name, encoding="utf-8")
    previews = tuple(
        _call(
            "run_action",
            {"action": "files.preview", "arguments": {"target": f"{name}/note.txt"}},
            f"run-{name}",
        )
        for name in ("a", "b")
    )
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}, "call-1"),)),
        _answer(calls=previews),
        _answer("Both read."),
    )
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "read both notes")
            await _replied(app, pilot)
            cards = list(app.query(ToolCard))

    assert len(cards) == 2
    assert all(card.has_class("-ok") for card in cards)


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
            await _dialog_open(app, pilot)
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
            await _dialog_open(app, pilot)
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
            assert "timed out" in _replies(app)[-1]

            app.query_one("#ai-input", Input).value = "again"
            app.query_one("#ai-send", Button).press()
            await _replied(app, pilot, count=2)
            assert _replies(app)[-1] == "Hi."


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
            assert not app.query_one("#ai-empty").display
            assert panel._agent is not None

            app.query_one("#ai-new", Button).press()
            await wait_until(pilot, lambda: not app.query(AgentTurn))

            assert panel._agent is None
            assert app.query_one("#ai-empty").display


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(140, 44), (90, 30)])
async def test_every_example_shows_whole(size):
    app = MaxDashboardApp()
    async with app.run_test(size=size) as pilot:
        app.navigate("ai")
        await pilot.pause()
        await pilot.pause()
        for button in app.query(".ai-example").results(Button):
            label = str(button.label)
            assert button.content_region.width >= len(label), label
            assert button.region.bottom <= size[1], label


@pytest.mark.asyncio
async def test_the_input_stays_in_view_as_the_chat_grows(ai_on):
    model = ScriptedModel(
        *[_answer(f"Answer {n}.\n\n" + "line\n\n" * 5) for n in range(6)]
    )
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            for n in range(6):
                await _send(app, pilot, f"request {n}")
                await _replied(app, pilot, count=n + 1)
            await pilot.pause()
            box = app.query_one("#ai-input", Input)
            log = app.query_one("#ai-log")

            assert box.region.bottom <= SIZE[1]
            assert log.max_scroll_y > 0  # the conversation scrolls, not the page
            assert app.query_one("#ai-panel").scroll_y == 0


@pytest.mark.asyncio
async def test_up_brings_back_the_last_request(ai_on):
    model = ScriptedModel(_answer("Done."))
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "shrink the videos")
            await _replied(app, pilot)
            box = app.query_one("#ai-input", Input)
            box.focus()
            await pilot.press("up")

            assert box.value == "shrink the videos"


@pytest.mark.asyncio
async def test_a_short_terminal_keeps_the_input_in_view(ai_on):
    model = ScriptedModel(_answer("A long answer.\n\n" + "More.\n\n" * 10))
    app = MaxDashboardApp()
    with patch(CLIENT_PATH, return_value=model):
        async with app.run_test(size=(80, 16)) as pilot:
            await _send(app, pilot, "hello")
            await _replied(app, pilot)
            await pilot.pause()
            box = app.query_one("#ai-input", Input)
            log = app.query_one("#ai-log")

            assert box.region.height and box.region.bottom <= 16
            assert log.allow_vertical_scroll and log.max_scroll_y > 0


@pytest.mark.asyncio
async def test_a_long_job_is_queued_and_shown_as_queued(ai_on, dummy_video):
    from max_cli.core.engines.task_manager import get_task_manager

    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "video"}, "call-1"),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {
                        "action": "video.compress",
                        "arguments": {"target": str(dummy_video)},
                        "queue": True,
                    },
                    "call-2",
                ),
            )
        ),
        _answer("Queued it; J shows progress."),
    )
    app = MaxDashboardApp()
    manager = get_task_manager()
    with patch(CLIENT_PATH, return_value=model), patch.object(manager, "start_worker"):
        async with app.run_test(size=SIZE) as pilot:
            await _send(app, pilot, "compress the video in the background")
            await _replied(app, pilot)
            [card] = app.query(ToolCard)

            assert card.has_class("-queued")
            assert "queued" in card.title
    assert [task.payload["action"] for task in manager.get_pending()] == [
        "video.compress"
    ]
