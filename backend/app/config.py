from pathlib import Path
from typing import Literal
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_database: str = "kontur"
    kontur_storage: Literal["mongodb", "memory", "local"] = "memory"
    kontur_data_dir: Path = ROOT / "runtime" / "projects"
    kontur_max_chars: int = 250_000
    kontur_max_calls: int = Field(default=80, ge=1, le=200)
    kontur_budget_usd: float = Field(default=0.50, gt=0, le=10)
    kontur_request_timeout: float = Field(default=75, ge=1, le=180)
    kontur_analysis_seconds: float = Field(default=600, ge=1, le=1800)
    kontur_max_output_tokens: int = Field(default=6000, ge=256, le=16000)
