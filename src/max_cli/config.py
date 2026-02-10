from pydantic_settings import BaseSettings
from typing import Optional


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
        env_file = ".env"


settings = Settings()
