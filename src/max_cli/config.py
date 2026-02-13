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

    class Config:
        # Pydantic will load these in order.
        # Files later in the list override earlier ones.
        env_file = [
            str(
                Path.home() / ".max_config.env"
            ),  # 1. Look in User Home (~/.max_config.env)
            ".env",  # 2. Look in Current Folder
        ]
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra keys in the file


settings = Settings()
