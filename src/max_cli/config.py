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

    # Models: 'gpt-5', 'gpt-5-nano', 'gemini-3.0-flash', 'gemini-3.0-pro'
    AI_MODEL: str = "gpt-5-nano"

    class Config:
        env_file = ".env"


settings = Settings()
