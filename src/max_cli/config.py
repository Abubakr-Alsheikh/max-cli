from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "Max CLI"
    DEFAULT_QUALITY: int = 85
    # This will load from OS Environment or .env file
    OPENAI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gpt-5-nano"

    class Config:
        env_file = ".env"


settings = Settings()
