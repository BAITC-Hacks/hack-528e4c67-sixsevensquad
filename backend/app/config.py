from pathlib import Path
from typing import Literal
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_database: str = "kontur"
    kontur_storage: Literal["mongodb", "memory"] = "memory"
    kontur_max_chars: int = 250_000
    kontur_max_calls: int = 80
