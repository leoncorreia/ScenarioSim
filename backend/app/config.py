from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    byteplus_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("BYTEPLUS_API_KEY", "ARK_API_KEY"),
    )
    byteplus_base_url: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    seedance_model: str = "seedance-1-5-pro-251215"
    video_ratio: str = "16:9"
    video_duration: int = 5
    video_resolution: str = "720p"
    generate_audio: bool = True

    demo_mode: bool = False
    fallback_mock_on_error: bool = True
    poll_interval_sec: float = 2.0
    poll_max_attempts: int = 120

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
