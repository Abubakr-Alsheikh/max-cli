"""One AI slot on the Settings page: the main AI or the fallback.

Pick a provider, and the slot shows only what that provider needs: its API
key (none for Ollama), a URL (a custom OpenAI-compatible service, or where
Ollama runs) and the model, picked from the list the provider offers that
key. The slot keeps what you type per provider, so switching to another
provider and back loses nothing, and it saves only the chosen provider's
settings. Test sends one tiny request with the values on screen, before
they're saved.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, Input, Label, Select, Static

from max_cli.core.engines.ai_providers import (
    GEMINI,
    OLLAMA,
    OPENAI,
    OPENROUTER,
    OPENROUTER_URL,
    PROVIDERS,
    SUGGESTED_MODELS,
    Provider,
)
from max_cli.interface.tui.workers import show_from_worker

MAIN = "main"
FALLBACK = "fallback"
ROLE_SETTINGS = {MAIN: "AI_PROVIDER", FALLBACK: "AI_FALLBACK_PROVIDER"}
NO_FALLBACK = ""
# Wait this long after the last key typed before reading the model list.
LIST_DELAY_SECONDS = 0.8
KEY_HINTS = {
    OPENAI: "platform.openai.com/api-keys",
    OPENROUTER: "openrouter.ai/keys",
    GEMINI: "aistudio.google.com/apikey (free)",
}
URL_HINTS = {
    OPENAI: "Empty for OpenAI; or any URL that speaks OpenAI's API",
    OLLAMA: "http://localhost:11434",
}
URL_LABELS = {OPENAI: "CUSTOM URL (EMPTY FOR OPENAI)", OLLAMA: "OLLAMA URL"}
PROVIDER_CHOICES = tuple((provider.label, name) for name, provider in PROVIDERS.items())


@dataclass
class Draft:
    """What the slot shows for one provider: saved, then as edited."""

    key: str = ""
    url: str = ""
    model: str = ""
    models: list[str] = field(default_factory=list)  # the provider's own list
    listed: bool = False  # `models` came from the provider


def slot_settings() -> frozenset[str]:
    """Every setting the AI slots edit, for the page's every-setting test."""
    names = set(ROLE_SETTINGS.values())
    for provider in PROVIDERS.values():
        names |= {provider.model_setting}
        names |= {name for name in (provider.key_setting, provider.url_setting) if name}
    return frozenset(names)


def saved_provider(role: str) -> str:
    """The provider a slot starts on: what's in use for the main AI (older
    settings without AI_PROVIDER included), the saved fallback or none."""
    from max_cli.config import settings
    from max_cli.core.engines.ai_providers import main_provider

    if role == MAIN:
        return main_provider().name
    fallback = settings.AI_FALLBACK_PROVIDER or NO_FALLBACK
    return fallback if fallback in PROVIDERS else NO_FALLBACK


def saved_draft(provider: Provider) -> Draft:
    from max_cli.config import settings

    key = getattr(settings, provider.key_setting) if provider.key_setting else ""
    return Draft(key=key or "", url=provider.saved_url(), model=provider.model())


class AISlot(Vertical):
    """The main AI or the fallback, with only the chosen provider's fields."""

    DEFAULT_CSS = """
    AISlot {
        height: auto;
        padding: 0 1 1 1;
        margin-bottom: 1;
        border-left: wide $primary 40%;
    }
    /* A Vertical takes 1fr by default: the field groups left big gaps. */
    AISlot Vertical {
        height: auto;
    }
    AISlot .slot-title {
        text-style: bold;
        color: $primary;
        margin-top: 1;
    }
    AISlot .slot-hint {
        color: $text-muted;
    }
    AISlot .slot-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    AISlot .slot-row {
        height: auto;
    }
    AISlot .slot-row Input, AISlot .slot-row Select {
        width: 1fr;
    }
    AISlot .slot-row Button {
        min-width: 10;
    }
    AISlot .slot-status {
        width: 1fr;
        padding: 1 1 0 1;
    }
    AISlot .slot-fields.-hidden, AISlot .slot-key.-hidden, AISlot .slot-url.-hidden {
        display: none;
    }
    """

    class ProviderChanged(Message):
        def __init__(self, slot: "AISlot", provider: str) -> None:
            super().__init__()
            self.slot = slot
            self.provider = provider

    def __init__(self, role: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.role = role
        self._drafts: dict[str, Draft] = {}
        self._saved: dict[str, Draft] = {}
        self._list_timer: Optional[Timer] = None
        self._shown = ""  # the provider whose fields are on screen
        self._exclude = ""  # the fallback can't be the main AI

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        title = "MAIN AI" if self.role == MAIN else "FALLBACK"
        hint = (
            "Answers the AI page, max ai and smart-sort."
            if self.role == MAIN
            else "Takes over when the main AI fails: no credit, a rate limit, a "
            "wrong key, the service down."
        )
        yield Static(title, classes="slot-title")
        yield Static(hint, classes="slot-hint")
        choices = list(PROVIDER_CHOICES)
        if self.role == FALLBACK:
            choices = [("No fallback", NO_FALLBACK), *choices]
        yield Select(choices, allow_blank=False, id=self._part_id("provider"))
        with Vertical(classes="slot-fields"):
            with Vertical(classes="slot-key"):
                yield Label("API KEY", classes="slot-label")
                with Horizontal(classes="slot-row"):
                    yield Input(password=True, id=self._part_id("key"))
                    yield Button("Show", id=self._part_id("reveal"))
            with Vertical(classes="slot-url"):
                yield Label("URL", classes="slot-label", id=self._part_id("url-label"))
                yield Input(id=self._part_id("url"))
            yield Label("MODEL", classes="slot-label")
            with Horizontal(classes="slot-row"):
                yield Select(
                    [],
                    prompt="Pick a model",
                    allow_blank=True,
                    id=self._part_id("model"),
                )
                yield Button("Reload list", id=self._part_id("reload"))
            with Horizontal(classes="slot-row"):
                yield Static("", classes="slot-status", id=self._part_id("status"))
                yield Button("Test", id=self._part_id("test"))

    def _part_id(self, part: str) -> str:
        return f"slot-{self.role}-{part}"

    def _part(self, part: str, kind: type) -> Any:
        return self.query_one(f"#{self._part_id(part)}", kind)

    # --- values -------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        select = self._part("provider", Select)
        return "" if select.is_blank() else str(select.value)

    @property
    def provider(self) -> Optional[Provider]:
        return PROVIDERS.get(self.provider_name)

    def load(self) -> None:
        """Show the saved settings, dropping any edits."""
        self._saved = {name: saved_draft(p) for name, p in PROVIDERS.items()}
        self._drafts = {name: Draft(**vars(d)) for name, d in self._saved.items()}
        self._show_provider(saved_provider(self.role))

    def exclude(self, provider: str) -> None:
        """The fallback can't be the main AI: drop it from the choices."""
        if self.role != FALLBACK or provider == self._exclude:
            return
        self._exclude = provider
        select = self._part("provider", Select)
        current = self.provider_name
        choices = [("No fallback", NO_FALLBACK)] + [
            choice for choice in PROVIDER_CHOICES if choice[1] != provider
        ]
        select.set_options(choices)
        select.value = current if current != provider else NO_FALLBACK
        self._show_provider(str(select.value))

    def _show_provider(self, name: str) -> None:
        """Fill the controls with `name`'s draft and show only its fields."""
        provider = PROVIDERS.get(name)
        self._shown = name
        select = self._part("provider", Select)
        if select.value != name:
            select.value = name
        self.query_one(".slot-fields").set_class(provider is None, "-hidden")
        if provider is not None:
            draft = self._drafts[name]
            needs_key = bool(provider.key_setting)
            needs_url = bool(provider.url_setting)
            self.query_one(".slot-key").set_class(not needs_key, "-hidden")
            self.query_one(".slot-url").set_class(not needs_url, "-hidden")
            key = self._part("key", Input)
            key.value = draft.key
            key.placeholder = KEY_HINTS.get(name, "")
            self._part("url-label", Label).update(URL_LABELS.get(name, "URL"))
            url = self._part("url", Input)
            url.value = draft.url
            url.placeholder = URL_HINTS.get(name, "")
            self._show_models(name)
        self._status_for(provider)

    def _show_models(self, name: str) -> None:
        draft = self._drafts[name]
        names = draft.models or list(SUGGESTED_MODELS.get(name, ()))
        if draft.model and draft.model not in names:
            names = [draft.model, *names]
        select = self._part("model", Select)
        select.set_options([(model, model) for model in names])
        if draft.model:
            select.value = draft.model
        else:
            select.clear()

    def _status_for(self, provider: Optional[Provider]) -> None:
        if provider is None:
            self._status("No fallback: when the main AI fails, Max says so.", "")
            return
        draft = self._drafts[provider.name]
        if provider.key_setting and not draft.key:
            self._status("Paste an API key, then pick a model.", "$warning")
        elif not draft.model:
            self._status("Pick a model.", "$warning")
        elif draft.listed:
            self._status(f"{len(draft.models)} models available.", "$text-muted")
        else:
            self._status("Test checks the key and model.", "$text-muted")

    def _status(self, text: str, style: str) -> None:
        self._part("status", Static).update(Content.styled(text, style or "$text"))

    def changes(self) -> dict[str, Optional[str]]:
        """Settings whose value differs from the saved one."""
        found: dict[str, Optional[str]] = {}
        name = self.provider_name
        if name != saved_provider(self.role):
            found[ROLE_SETTINGS[self.role]] = name
        provider = self.provider
        if provider is None:
            return found
        draft, saved = self._drafts[name], self._saved[name]
        for setting, value, before in (
            (provider.key_setting, draft.key, saved.key),
            (provider.url_setting, draft.url, saved.url),
            (provider.model_setting, draft.model, saved.model),
        ):
            if setting and value.strip() != before:
                found[setting] = value.strip() or None
        return found

    # --- events ---------------------------------------------------------------

    # Change events arrive after the code that set a control has finished,
    # so each handler compares with what the slot shows: setting a control
    # from code (load, switching provider) is never taken for an edit.

    @on(Select.Changed)
    def _on_select(self, event: Select.Changed) -> None:
        # Selects fire once when they mount, before load() fills the drafts.
        if not self._drafts:
            return
        value = "" if event.select.is_blank() else str(event.value)
        if event.select.id == self._part_id("provider"):
            if value == self._shown:
                return
            self._adopt_custom_key(value)
            self._show_provider(value)
            self.post_message(self.ProviderChanged(self, value))
            self._list_soon()
        elif event.select.id == self._part_id("model") and self.provider is not None:
            draft = self._drafts[self.provider_name]
            if value and value != draft.model:
                draft.model = value
                self._status_for(self.provider)

    @on(Input.Changed)
    def _on_input(self, event: Input.Changed) -> None:
        if not self._drafts or self.provider is None:
            return
        draft = self._drafts[self.provider_name]
        if event.input.id == self._part_id("key") and event.value != draft.key:
            draft.key = event.value
        elif event.input.id == self._part_id("url") and event.value != draft.url:
            draft.url = event.value
        else:
            return
        draft.listed = False
        self._list_soon()
        self._status_for(self.provider)

    def _adopt_custom_key(self, name: str) -> None:
        """Switching to OpenRouter with no key of its own, while OpenAI's key
        is set for OpenRouter's URL: that key is the OpenRouter key."""
        if name != OPENROUTER or self._drafts[OPENROUTER].key:
            return
        openai = self._drafts[OPENAI]
        if openai.key and openai.url.rstrip("/") == OPENROUTER_URL:
            self._drafts[OPENROUTER].key = openai.key

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == self._part_id("reveal"):
            event.stop()
            key = self._part("key", Input)
            key.password = not key.password
            event.button.label = "Show" if key.password else "Hide"
        elif button_id == self._part_id("reload"):
            event.stop()
            self._list_models()
        elif button_id == self._part_id("test"):
            event.stop()
            self._test()

    # --- the provider's model list, and Test ------------------------------------

    def refresh_models(self) -> None:
        """Read the chosen provider's model list (the page asks when shown)."""
        draft = self._drafts.get(self.provider_name)
        if draft is not None and not draft.listed:
            self._list_models()

    def _list_soon(self) -> None:
        if self._list_timer is not None:
            self._list_timer.stop()
        self._list_timer = self.set_timer(LIST_DELAY_SECONDS, self._list_models)

    def _list_models(self) -> None:
        provider = self.provider
        if provider is None:
            return
        draft = self._drafts[provider.name]
        if provider.key_setting and not draft.key:
            return
        self._status("Reading the model list...", "$primary")
        name, key, url = provider.name, draft.key or None, draft.url
        self.run_worker(
            lambda: self._list_in_thread(name, key, url),
            thread=True,
            exclusive=True,
            group=f"slot-{self.role}-models",
        )

    def _list_in_thread(self, name: str, key: Optional[str], url: str) -> None:
        from openai import APIError

        from max_cli.core.engines.ai_providers import error_text, list_models

        try:
            models, problem = list_models(PROVIDERS[name], key, url), ""
        except APIError as e:
            models, problem = [], error_text(e)
        show_from_worker(self, self._show_listed, name, models, problem)

    def _show_listed(self, name: str, models: list[str], problem: str) -> None:
        draft = self._drafts[name]
        if problem:
            if name == self.provider_name:
                self._status(f"Couldn't read the models: {problem}", "$warning")
            return
        draft.models, draft.listed = models, True
        if name == self.provider_name:
            self._show_models(name)
            self._status_for(self.provider)

    def _test(self) -> None:
        provider = self.provider
        if provider is None:
            return
        draft = self._drafts[provider.name]
        self._status("Testing...", "$primary")
        self._part("test", Button).disabled = True
        name, key, url, model = provider.name, draft.key or None, draft.url, draft.model

        def run() -> None:
            from max_cli.core.engines.ai_providers import check

            outcome = check(PROVIDERS[name], key, url, model)
            show_from_worker(self, self._show_test, name, outcome)

        self.run_worker(
            run, thread=True, exclusive=True, group=f"slot-{self.role}-test"
        )

    def _show_test(self, name: str, outcome: str) -> None:
        self._part("test", Button).disabled = False
        if name != self.provider_name:
            return
        if outcome == "OK":
            self._status(f"✓ Works: {self._drafts[name].model} answered.", "$success")
        else:
            self._status(f"✗ {outcome}", "$error")
