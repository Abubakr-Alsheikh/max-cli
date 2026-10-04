from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# Settings Max read once and no longer has. Settings ignores them in a
# settings file (extra = "ignore"); the dashboard and `max config validate`
# point them out so you can remove them.
REMOVED_SETTINGS = (
    "APP_NAME",
    "BATCH_SIZE",
    "GRAB_AUDIO_FORMAT",
    "GRAB_QUEUE_ENABLED",
    "PROGRESS_BAR",
    "VERBOSE",
)


class Settings(BaseSettings):
    DEFAULT_QUALITY: int = 85

    MAX_WORKERS: int = Field(default=4, ge=1, le=16)

    # Seconds a download may wait for data before it gives up or retries:
    # videos, FFmpeg, the noise model, AI images.
    # No upper limits: these existed, unread, without one, and a settings
    # file that set a big value must still load.
    DOWNLOAD_TIMEOUT: int = Field(default=60, ge=10)
    # How many more times the queue runs a task that failed.
    MAX_RETRIES: int = Field(default=2, ge=0)
    # Ask before moving, overwriting or deleting files. Off works like
    # --force everywhere, except `files shred`, which can't be undone.
    CONFIRM_DESTRUCTIVE: bool = True

    # AI Configuration
    # If using OpenAI, leave BASE_URL as None.
    # If using Gemini, set to: https://generativelanguage.googleapis.com/v1beta/openai/
    # If using Ollama, set to: http://localhost:11434/v1
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    # Models
    # OpenAI's (or OPENAI_BASE_URL's) chat and image models
    AI_MODEL: str = "gpt-6-luna"
    AI_IMAGE_MODEL: str = "gpt-image-2.5-flare"

    # Main provider and fallback: openai, openrouter, gemini or ollama
    # (core/engines/ai_providers.py). An empty AI_PROVIDER keeps what older
    # settings meant: Ollama when OLLAMA_ENABLED, else OpenAI.
    AI_PROVIDER: str = ""
    AI_FALLBACK_PROVIDER: str = ""
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = ""  # picked on the Settings page
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = ""
    # Image models per provider (OpenAI's is AI_IMAGE_MODEL); "" for none.
    OPENROUTER_IMAGE_MODEL: str = ""
    GEMINI_IMAGE_MODEL: str = ""

    # Ollama Configuration
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # --- GRAB (DOWNLOADER) DEFAULTS ---
    # These save your preferences
    GRAB_QUALITY: str = "h"  # s, m, h, x
    GRAB_STRIP_PLAYLIST: bool = True  # If True, removes '&list=...' from video URLs
    GRAB_INCLUDE_METADATA: bool = True  # If True, embeds tags/thumbnails

    # New: Default path and type for downloads
    GRAB_DEFAULT_PATH: Path = Path.home() / "Max Downloads"
    GRAB_DEFAULT_TYPE: str = "video"  # "video" or "audio"
    GRAB_MAX_CONCURRENT: int = Field(
        default=3, ge=1, le=8
    )  # dashboard downloads at once

    # --- DASHBOARD ---
    # Page icons: "codes" (a colour bar and the page's key code), or a glyph
    # before each name: "nerd" (needs a Nerd Font such as Cascadia Code NF as
    # the terminal's font) or "emoji".
    DASHBOARD_ICONS: str = "codes"

    class Config:
        env_file = [str(Path.home() / ".max_config.env"), ".env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


def load_settings() -> Settings:
    """Settings from the environment and the settings files.

    A bad value (MAX_WORKERS=99) raises ConfigurationError, which `main()`
    prints as one line naming the setting, instead of a crash report.
    """
    from pydantic import ValidationError

    from max_cli.common.exceptions import ConfigurationError

    try:
        return Settings()
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in e.errors()
        )
        raise ConfigurationError(
            f"A setting has a bad value ({problems}). Fix or delete that line "
            "in ~/.max_config.env, or in a .env file in this folder."
        ) from None


settings = load_settings()
