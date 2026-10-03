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
DEFAULT_OLLAMA_URL = "http://localhost:11434"
CHECK_PROMPT = "Reply with the word OK."
CHAT_API = "chat.completions.create"
IMAGES_GENERATE = "images.generate"
IMAGES_EDIT = "images.edit"
CHECK_MAX_TOKENS = 5


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    key_setting: str  # "" for Ollama, which needs no key
    model_setting: str
    url: str = ""  # a fixed endpoint; "" reads url_setting
    url_setting: str = ""
    image_setting: str = ""  # the image model's setting; "" for no images

    def key(self) -> Optional[str]:
        if not self.key_setting:
            return OLLAMA_KEY
        return getattr(settings, self.key_setting) or None

    def saved_url(self) -> str:
        """The URL setting as saved (OPENAI_BASE_URL, OLLAMA_BASE_URL); ""
        for a provider with a fixed endpoint."""
        return (
            str(getattr(settings, self.url_setting) or "") if self.url_setting else ""
        )

    def base_url(self, url: Optional[str] = None) -> Optional[str]:
        """The endpoint the client talks to; `url` replaces the saved URL
        setting (the Settings page checks values before they're saved)."""
        typed = self.saved_url() if url is None else url
        if self.name == OLLAMA:
            return f"{(typed or DEFAULT_OLLAMA_URL).rstrip('/')}/v1"
        return self.url or typed or None

    def model(self) -> str:
        return str(getattr(settings, self.model_setting) or "")

    def image_model(self) -> str:
        """The model `max ai create` and `edit` use; "" when none."""
        if not self.image_setting:
            return ""
        return str(getattr(settings, self.image_setting) or "")

    def model_for(self, image: bool) -> str:
        return self.image_model() if image else self.model()

    def is_set_up(self) -> bool:
        """It has a key (Ollama needs none) and a model."""
        return bool(self.key()) and bool(self.model())

    def missing(self) -> str:
        """What it still needs, in a few words; "" when it's set up."""
        if not self.key():
            return "no API key"
        if not self.model():
            return "no model picked"
        return ""


PROVIDERS: dict[str, Provider] = {
    OPENAI: Provider(
        OPENAI,
        "OpenAI or compatible",
        "OPENAI_API_KEY",
        "AI_MODEL",
        url_setting="OPENAI_BASE_URL",
        image_setting="AI_IMAGE_MODEL",
    ),
    OPENROUTER: Provider(
        OPENROUTER,
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        OPENROUTER_URL,
        image_setting="OPENROUTER_IMAGE_MODEL",
    ),
    GEMINI: Provider(
        GEMINI,
        "Google Gemini",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        GEMINI_URL,
        image_setting="GEMINI_IMAGE_MODEL",
    ),
    OLLAMA: Provider(
        OLLAMA,
        "Ollama (this computer)",
        "",
        "OLLAMA_MODEL",
        url_setting="OLLAMA_BASE_URL",
    ),
}
# Offered when a provider's own list can't be read (no key yet, offline).
# Checked against the providers' docs on 2026-10-03; the live list wins.
SUGGESTED_MODELS: dict[str, tuple[str, ...]] = {
    OPENAI: ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"),
    OPENROUTER: ("openrouter/free", "openrouter/auto"),
    # The -latest aliases follow Google's newest release of each family.
    GEMINI: (
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ),
    OLLAMA: ("llama3.1", "qwen2.5", "mistral"),
}
SUGGESTED_IMAGE_MODELS: dict[str, tuple[str, ...]] = {
    OPENAI: ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst"),
    OPENROUTER: (
        "google/gemini-2.5-flash-image",
        "openai/gpt-image-2",
        "black-forest-labs/flux.2-pro",
    ),
    # Nano Banana 2, its Lite, Nano Banana Pro, Nano Banana.
    GEMINI: (
        "gemini-3.1-flash-image",
        "gemini-3.1-flash-lite-image",
        "gemini-3-pro-image",
        "gemini-2.5-flash-image",
    ),
    OLLAMA: (),
}
# Model ids that make images, for the image model list.
IMAGE_WORDS = ("image", "imagen", "dall-e", "flux", "seedream")
# Model ids that aren't chat models, left out of a provider's list.
NOT_CHAT = (
    *IMAGE_WORDS,
    "embedding",
    "embed",
    "tts",
    "transcribe",
    "whisper",
    "audio",
    "realtime",
    "moderation",
    "aqa",
    "veo",
    "lyria",
)


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
    return [provider for provider in _main_and_fallback() if provider.is_set_up()]


def _openai_client(
    provider: Provider, key: Optional[str] = None, url: Optional[str] = None
) -> Any:
    """A client for `provider`; `key` and `url` replace the saved ones."""
    from openai import OpenAI

    return OpenAI(api_key=key or provider.key(), base_url=provider.base_url(url))


def all_models(
    provider: Provider, key: Optional[str] = None, url: Optional[str] = None
) -> list[str]:
    """Every model the provider offers this key, sorted ([] without a key).
    Raises the openai error when it can't list them."""
    if provider.key_setting and not (key or provider.key()):
        return []
    found = _openai_client(provider, key, url).models.list()
    return sorted({str(model.id).removeprefix("models/") for model in found})


def chat_models(names: list[str]) -> list[str]:
    return [name for name in names if not any(w in name.lower() for w in NOT_CHAT)]


def image_models(names: list[str]) -> list[str]:
    return [name for name in names if any(w in name.lower() for w in IMAGE_WORDS)]


def list_models(
    provider: Provider,
    key: Optional[str] = None,
    url: Optional[str] = None,
    image: bool = False,
) -> list[str]:
    """The chat models (or with `image`, the image models) the provider
    offers this key, sorted."""
    names = all_models(provider, key, url)
    return image_models(names) if image else chat_models(names)


class _Completions:
    def __init__(self, owner: "FallbackClient") -> None:
        self._owner = owner

    def create(self, **request: Any) -> Any:
        return self._owner.call(CHAT_API, **request)


class _Chat:
    def __init__(self, owner: "FallbackClient") -> None:
        self.completions = _Completions(owner)


class _Images:
    """The images endpoint: OpenAI, Gemini and OpenRouter all make images
    there, not through chat."""

    def __init__(self, owner: "FallbackClient") -> None:
        self._owner = owner

    def generate(self, **request: Any) -> Any:
        return self._owner.call(IMAGES_GENERATE, **request)

    def edit(self, **request: Any) -> Any:
        return self._owner.call(IMAGES_EDIT, **request)


class FallbackClient:
    """`client.chat.completions.create(...)` and `client.images.generate(...)`
    / `.edit(...)` across the main provider and the fallback. Each provider
    uses its own model: the `model` a caller passes is ignored.
    `last_provider` says who answered."""

    def __init__(
        self,
        providers: list[Provider],
        image: bool = False,
        model: Optional[str] = None,
    ) -> None:
        """`image` sends each provider its image model; `model` names one
        model for every provider (`max ai create -m`)."""
        self.providers = providers
        self.image = image
        self._model = model
        self._clients: dict[str, Any] = {}
        self._start = 0  # the provider that worked last
        self.last_provider: Provider = providers[0]
        self.chat = _Chat(self)
        self.images = _Images(self)

    def _model_of(self, provider: Provider) -> str:
        return self._model or provider.model_for(self.image)

    @property
    def model(self) -> str:
        """The model the next request goes to."""
        return self._model_of(self.providers[self._start])

    def _client(self, provider: Provider) -> Any:
        if provider.name not in self._clients:
            self._clients[provider.name] = _openai_client(provider)
        return self._clients[provider.name]

    def call(self, api: str, **request: Any) -> Any:
        """`api` ("chat.completions.create", "images.generate" ...) on the
        provider that worked last, then on the next ones when it fails."""
        from openai import APIError

        request.pop("model", None)
        tries = range(self._start, len(self.providers))
        for index in tries:
            provider = self.providers[index]
            try:
                method = self._client(provider)
                for part in api.split("."):
                    method = getattr(method, part)
                response = method(model=self._model_of(provider), **request)
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


def make_client(
    image: bool = False, model: Optional[str] = None
) -> Optional[FallbackClient]:
    """A client over the main provider and the fallback; None when neither
    is set up. `image` uses their image models (only providers that have
    one); `model` names a model for every provider."""
    if not image:
        chain = provider_chain()
    else:
        chain = [
            provider
            for provider in _main_and_fallback()
            if provider.key() and (model or provider.image_model())
        ]
    return FallbackClient(chain, image=image, model=model) if chain else None


def _main_and_fallback() -> list[Provider]:
    fallback = fallback_provider()
    return [main_provider(), *([fallback] if fallback is not None else [])]


def chat_model() -> str:
    """The main provider's model."""
    return main_provider().model()


def check(
    provider: Provider,
    key: Optional[str] = None,
    url: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Send a tiny request; "OK", or what went wrong in a few words. `key`,
    `url` and `model` replace the saved ones."""
    from openai import APIError

    if provider.key_setting and not (key or provider.key()):
        return "no API key"
    model = model if model is not None else provider.model()
    if not model:
        return "no model picked"
    try:
        _openai_client(provider, key, url).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": CHECK_PROMPT}],
            max_tokens=CHECK_MAX_TOKENS,
        )
    except APIError as e:
        return error_text(e)
    return "OK"


STATUS_TEXT = {
    401: "the API key is wrong (401)",
    402: "no credit left (402)",
    403: "the key may not use this model (403)",
    404: "unknown model (404)",
    429: "quota or rate limit reached (429)",
}


def error_text(error: Exception) -> str:
    """An openai error in a few words, for the Settings page."""
    from openai import APIConnectionError, APIStatusError

    if isinstance(error, APIConnectionError):
        return "can't reach it"
    if isinstance(error, APIStatusError):
        return _status_text(error.status_code)
    return str(error)[:80]


def _status_text(status: int) -> str:
    if status in STATUS_TEXT:
        return STATUS_TEXT[status]
    if status >= 500:
        return f"the service is down ({status})"
    return f"refused ({status})"
