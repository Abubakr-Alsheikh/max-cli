from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Global configuration managed via Environment Variables."""

    APP_NAME: str = "Max CLI"
    DEFAULT_QUALITY: int = 85
    OPENAI_API_KEY: str | None = None

    # AI Personality settings
    AI_MODEL: str = "gpt-5-nano"

    class Config:
        env_file = ".env"


settings = Settings()
