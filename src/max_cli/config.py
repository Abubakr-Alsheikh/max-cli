from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "Max CLI"
    DEFAULT_QUALITY: int = 85

    MAX_WORKERS: int = Field(default=4, ge=1, le=16)
    BATCH_SIZE: int = Field(default=10, ge=1)

    DOWNLOAD_TIMEOUT: int = Field(default=300, ge=30)
    MAX_RETRIES: int = Field(default=3, ge=0)

    PROGRESS_BAR: bool = True
    VERBOSE: bool = False
    CONFIRM_DESTRUCTIVE: bool = True

    # AI Configuration
    # If using OpenAI, leave BASE_URL as None.
    # If using Gemini, set to: https://generativelanguage.googleapis.com/v1beta/openai/
    # If using Ollama, set to: http://localhost:11434/v1
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    # Models
    AI_MODEL: str = "gpt-5-nano"  # For 'ask', 'chat', 'analyze'
    AI_IMAGE_MODEL: str = "gpt-image-1"  # For 'create', 'edit'

    # Ollama Configuration
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # --- GRAB (DOWNLOADER) DEFAULTS ---
    # These save your preferences
    GRAB_QUALITY: str = "h"  # s, m, h, x
    GRAB_AUDIO_FORMAT: str = "mp3"  # mp3, m4a, wav
    GRAB_STRIP_PLAYLIST: bool = True  # If True, removes '&list=...' from video URLs
    GRAB_INCLUDE_METADATA: bool = True  # If True, embeds tags/thumbnails

    # New: Default path and type for downloads
    GRAB_DEFAULT_PATH: Path = Path.home() / "Max Downloads"
    GRAB_DEFAULT_TYPE: str = "video"  # "video" or "audio"
    GRAB_QUEUE_ENABLED: bool = False

    class Config:
        env_file = [str(Path.home() / ".max_config.env"), ".env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
