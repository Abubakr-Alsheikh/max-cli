"""core/engines/ai_providers.py: main provider, fallback, per-provider keys."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import openai
import pytest

from max_cli.config import settings
from max_cli.core.engines import ai_providers
from max_cli.core.engines.ai_providers import (
    GEMINI_URL,
    OPENROUTER_URL,
    FallbackClient,
    check,
    main_provider,
    make_client,
    provider_chain,
)


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    """Start from nothing set up."""
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(settings, name, None)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None)
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")


def _api_error(cls: type, message: str = "nope", status: int = 0) -> Exception:
    """An openai error without building an HTTP response: openai 1-2 build
    them from httpx, openai 3 from httpx2."""
    error = cls.__new__(cls)
    Exception.__init__(error, message)
    if status:
        error.status_code = status
    return error


class FakeProvider:
    """One provider's client: answers, or raises the given error."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.models: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.models.append(request["model"])
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


# --- which provider -----------------------------------------------------------


@pytest.mark.parametrize("ollama, expected", [(True, "ollama"), (False, "openai")])
def test_older_settings_keep_their_provider(monkeypatch, ollama, expected):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", ollama)

    assert main_provider().name == expected


def test_the_chain_is_main_then_fallback_with_keys_only(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-key")

    assert [p.name for p in provider_chain()] == ["openrouter"]  # gemini: no key

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    assert [p.name for p in provider_chain()] == ["openrouter", "gemini"]


def test_a_fallback_equal_to_the_main_provider_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")

    assert [p.name for p in provider_chain()] == ["gemini"]


def test_without_any_key_there_is_no_client():
    assert make_client() is None


@pytest.mark.parametrize(
    "provider, key_setting, url",
    [
        ("gemini", "GEMINI_API_KEY", GEMINI_URL),
        ("openrouter", "OPENROUTER_API_KEY", OPENROUTER_URL),
    ],
)
def test_each_provider_uses_its_own_key_and_url(
    monkeypatch, provider, key_setting, url
):
    monkeypatch.setattr(settings, "AI_PROVIDER", provider)
    monkeypatch.setattr(settings, key_setting, "secret")
    reply = SimpleNamespace(choices=[])

    with patch("openai.OpenAI") as client_class:
        client_class.return_value.chat.completions.create.return_value = reply
        assert make_client().chat.completions.create(messages=[]) is reply

    client_class.assert_called_once_with(api_key="secret", base_url=url)


# --- falling back -------------------------------------------------------------


def _two_providers(monkeypatch, main: FakeProvider, fallback: FakeProvider):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    fakes = {"openrouter": main, "gemini": fallback}
    monkeypatch.setattr(ai_providers, "_openai_client", lambda p: fakes[p.name])
    client = make_client()
    assert isinstance(client, FallbackClient)
    return client


def test_a_failing_main_provider_falls_back_and_stays_there(monkeypatch):
    out_of_credit = _api_error(openai.APIStatusError, "Payment required", 402)
    main, fallback = FakeProvider(out_of_credit), FakeProvider("answer")
    client = _two_providers(monkeypatch, main, fallback)

    first = client.chat.completions.create(model="ignored", messages=[])
    second = client.chat.completions.create(model="ignored", messages=[])

    assert first == second == "answer"
    assert main.models == ["openrouter/free"]  # tried once, then skipped
    assert fallback.models == ["gemini-2.5-flash", "gemini-2.5-flash"]
    assert client.last_provider.name == "gemini" and client.used_fallback
    assert client.model == "gemini-2.5-flash"


def test_when_every_provider_fails_the_last_error_is_raised(monkeypatch):
    main = FakeProvider(_api_error(openai.APIStatusError, "limit", 429))
    fallback = FakeProvider(_api_error(openai.APIConnectionError, "down"))
    client = _two_providers(monkeypatch, main, fallback)

    with pytest.raises(openai.APIConnectionError):
        client.chat.completions.create(messages=[])


def test_a_working_main_provider_never_touches_the_fallback(monkeypatch):
    main, fallback = FakeProvider("main answer"), FakeProvider("unused")
    client = _two_providers(monkeypatch, main, fallback)

    assert client.chat.completions.create(messages=[]) == "main answer"
    assert fallback.models == []
    assert not client.used_fallback


def test_a_provider_without_a_model_is_not_set_up(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "")

    gemini = ai_providers.PROVIDERS["gemini"]
    assert not gemini.is_set_up() and gemini.missing() == "no model picked"
    assert make_client() is None


# --- listing models -----------------------------------------------------------


def test_list_models_keeps_chat_models_without_the_models_prefix(monkeypatch):
    listed = [
        SimpleNamespace(id=name)
        for name in (
            "models/gemini-2.5-flash",
            "models/gemini-2.5-pro",
            "models/text-embedding-004",
            "models/imagen-3.0",
        )
    ]
    fake = SimpleNamespace(models=SimpleNamespace(list=lambda: listed))
    seen = {}

    def client(provider, key=None, url=None):
        seen.update(key=key, url=url)
        return fake

    monkeypatch.setattr(ai_providers, "_openai_client", client)

    names = ai_providers.list_models(ai_providers.PROVIDERS["gemini"], key="typed")

    assert names == ["gemini-2.5-flash", "gemini-2.5-pro"]
    assert seen["key"] == "typed"  # the key typed on the page, before saving


def test_list_models_without_a_key_lists_nothing():
    assert ai_providers.list_models(ai_providers.PROVIDERS["openrouter"]) == []


# --- checking a provider ------------------------------------------------------


@pytest.mark.parametrize(
    "error, expected",
    [
        (None, "OK"),
        (_api_error(openai.APIStatusError, "x", 402), "no credit left (402)"),
        (_api_error(openai.APIStatusError, "x", 401), "the API key is wrong (401)"),
        (_api_error(openai.APIStatusError, "x", 503), "the service is down (503)"),
        (_api_error(openai.APIConnectionError, "x"), "can't reach it"),
    ],
)
def test_check_says_what_works(monkeypatch, error, expected):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    fake = FakeProvider(error if error is not None else "OK")
    monkeypatch.setattr(ai_providers, "_openai_client", lambda *args: fake)

    assert check(ai_providers.PROVIDERS["gemini"]) == expected


def test_check_without_a_key_says_so():
    assert check(ai_providers.PROVIDERS["openrouter"]) == "no API key"


def test_image_requests_use_each_providers_image_model(monkeypatch):
    main, fallback = (
        FakeProvider(_api_error(openai.APIStatusError, "x", 429)),
        FakeProvider("img"),
    )
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(
        settings, "OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"
    )
    monkeypatch.setattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    fakes = {"openrouter": main, "gemini": fallback}
    monkeypatch.setattr(ai_providers, "_openai_client", lambda p: fakes[p.name])

    client = make_client(image=True)

    assert client.chat.completions.create(messages=[]) == "img"
    assert main.models == ["google/gemini-2.5-flash-image"]
    assert fallback.models == ["gemini-3.1-flash-image"]


def test_a_provider_without_an_image_model_is_left_out_of_images(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(settings, "GEMINI_IMAGE_MODEL", "")

    assert make_client(image=True) is None
    assert make_client(image=True, model="gemini-3-pro-image") is not None
