from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "Max CLI"
    DEFAULT_QUALITY: int = 85

    # AI Configuration
    # If using OpenAI, leave BASE_URL as None.
    # If using Gemini, set to: https://generativelanguage.googleapis.com/v1beta/openai/
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    # Models
    AI_MODEL: str = "gpt-5-nano"  # For 'ask', 'chat', 'analyze'
    AI_IMAGE_MODEL: str = "gemini-2.5-flash-image"  # For 'create', 'edit'

    # --- GRAB (DOWNLOADER) DEFAULTS ---
    # These save your preferences
    GRAB_QUALITY: str = "h"  # s, m, h, x
    GRAB_AUDIO_FORMAT: str = "mp3"  # mp3, m4a, wav
    GRAB_STRIP_PLAYLIST: bool = True  # If True, removes '&list=...' from video URLs
    GRAB_INCLUDE_METADATA: bool = True  # If True, embeds tags/thumbnails

    class Config:
        env_file = [str(Path.home() / ".max_config.env"), ".env"]
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
