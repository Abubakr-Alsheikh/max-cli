"""Which AI Max talks to: a main provider and a fallback, each with its own key.

Every provider speaks the OpenAI chat API: OpenAI (or any URL that speaks
it), OpenRouter, Gemini (Google's OpenAI-compatible endpoint) and Ollama on
this computer. `make_client` returns a `FallbackClient`: a request goes to
the main provider, and when that fails (quota or credit used up, a wrong
key, an unknown model, the service down) the same request goes to the
fallback. After a failure the client stays on the provider that worked for
the rest of its life, so a dead provider doesn't cost every request a
round trip.

With AI_PROVIDER unset, Max picks what older settings files meant: Ollama
when OLLAMA_ENABLED is on, else OpenAI with OPENAI_API_KEY and
OPENAI_BASE_URL.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from max_cli.config import settings

logger = logging.getLogger(__name__)

OPENAI = "openai"
OPENROUTER = "openrouter"
GEMINI = "gemini"
OLLAMA = "ollama"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_KEY = "ollama"  # Ollama ignores the key, but the client needs one
CHECK_PROMPT = "Reply with the word OK."
CHECK_MAX_TOKENS = 5


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    key_setting: str  # "" for Ollama, which needs no key
    model_setting: str
    url: str = ""  # a fixed endpoint; "" reads url_setting
    url_setting: str = ""

    def key(self) -> Optional[str]:
        if not self.key_setting:
            return OLLAMA_KEY
        return getattr(settings, self.key_setting) or None

    def base_url(self) -> Optional[str]:
        if self.name == OLLAMA:
            return f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1"
        if self.url:
            return self.url
        return getattr(settings, self.url_setting) or None if self.url_setting else None

    def model(self) -> str:
        return str(getattr(settings, self.model_setting))

    def is_set_up(self) -> bool:
        """It has a key (Ollama needs none)."""
        return bool(self.key())


PROVIDERS: dict[str, Provider] = {
    OPENAI: Provider(
        OPENAI,
        "OpenAI (or a custom URL)",
        "OPENAI_API_KEY",
        "AI_MODEL",
        url_setting="OPENAI_BASE_URL",
    ),
    OPENROUTER: Provider(
        OPENROUTER,
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        OPENROUTER_URL,
    ),
    GEMINI: Provider(
        GEMINI, "Google Gemini", "GEMINI_API_KEY", "GEMINI_MODEL", GEMINI_URL
    ),
    OLLAMA: Provider(OLLAMA, "Ollama (this computer)", "", "OLLAMA_MODEL"),
}


def main_provider() -> Provider:
    """AI_PROVIDER, or what older settings meant (see the module doc)."""
    name = settings.AI_PROVIDER or (OLLAMA if settings.OLLAMA_ENABLED else OPENAI)
    return PROVIDERS.get(name, PROVIDERS[OPENAI])


def fallback_provider() -> Optional[Provider]:
    fallback = PROVIDERS.get(settings.AI_FALLBACK_PROVIDER or "")
    if fallback is None or fallback.name == main_provider().name:
        return None
    return fallback


def provider_chain() -> list[Provider]:
    """The providers to try in order, those with a key only."""
    chain = [main_provider()]
    fallback = fallback_provider()
    if fallback is not None:
        chain.append(fallback)
    return [provider for provider in chain if provider.is_set_up()]


def _openai_client(provider: Provider) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=provider.key(), base_url=provider.base_url())


class _Completions:
    def __init__(self, owner: "FallbackClient") -> None:
        self._owner = owner

    def create(self, **request: Any) -> Any:
        return self._owner.complete(**request)


class _Chat:
    def __init__(self, owner: "FallbackClient") -> None:
        self.completions = _Completions(owner)


class FallbackClient:
    """`client.chat.completions.create(...)` across the main provider and
    the fallback. Each provider uses its own model: the `model` a caller
    passes is ignored. `last_provider` and `last_model` say who answered."""

    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers
        self._clients: dict[str, Any] = {}
        self._start = 0  # the provider that worked last
        self.last_provider: Provider = providers[0]
        self.chat = _Chat(self)

    @property
    def model(self) -> str:
        """The model the next request goes to."""
        return self.providers[self._start].model()

    def _client(self, provider: Provider) -> Any:
        if provider.name not in self._clients:
            self._clients[provider.name] = _openai_client(provider)
        return self._clients[provider.name]

    def complete(self, **request: Any) -> Any:
        from openai import APIError

        request.pop("model", None)
        tries = range(self._start, len(self.providers))
        for index in tries:
            provider = self.providers[index]
            try:
                response = self._client(provider).chat.completions.create(
                    model=provider.model(), **request
                )
            except APIError as e:
                if index == tries[-1]:
                    raise  # the last provider failed too
                logger.warning(
                    "%s failed (%s); trying %s",
                    provider.label,
                    e,
                    self.providers[index + 1].label,
                )
                continue
            self._start = index
            self.last_provider = provider
            return response
        raise RuntimeError(
            "FallbackClient has no providers"
        )  # make_client never builds one

    @property
    def used_fallback(self) -> bool:
        return self.last_provider.name != self.providers[0].name


def make_client() -> Optional[FallbackClient]:
    """A client over the main provider and the fallback; None when neither
    has a key."""
    chain = provider_chain()
    return FallbackClient(chain) if chain else None


def chat_model() -> str:
    """The main provider's model."""
    return main_provider().model()


def check(provider: Provider) -> str:
    """Send a tiny request; "OK", or what went wrong in a few words."""
    from openai import APIConnectionError, APIError, APIStatusError

    if not provider.is_set_up():
        return "no API key"
    try:
        _openai_client(provider).chat.completions.create(
            model=provider.model(),
            messages=[{"role": "user", "content": CHECK_PROMPT}],
            max_tokens=CHECK_MAX_TOKENS,
        )
    except APIConnectionError:
        return "can't reach it"
    except APIStatusError as e:
        return _status_text(e.status_code)
    except APIError as e:
        return str(e)[:80]
    return "OK"


STATUS_TEXT = {
    401: "the API key is wrong (401)",
    402: "no credit left (402)",
    403: "the key may not use this model (403)",
    404: "unknown model (404)",
    429: "quota or rate limit reached (429)",
}


def _status_text(status: int) -> str:
    if status in STATUS_TEXT:
        return STATUS_TEXT[status]
    if status >= 500:
        return f"the service is down ({status})"
    return f"refused ({status})"
