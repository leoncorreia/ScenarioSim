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
    seedance_model: str = "dreamina-seedance-2-0-260128"
    video_ratio: str = "16:9"
    # Dreamina Seedance 2.0: duration 4–15 s per ModelArk model list.
    video_duration: int = 6
    # 2.0 supports 480p / 720p (not 1080p like some 1.x models).
    video_resolution: str = "720p"
    generate_audio: bool = True

    demo_mode: bool = False
    fallback_mock_on_error: bool = True
    poll_interval_sec: float = 2.0
    poll_max_attempts: int = 120

    # Optional reproducibility: non-negative int → passed to Seedance as seed+variant_index; omit if unset.
    seedance_seed: int | None = None
    batch_jobs_max: int = 25

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Recommendation blurbs: ModelArk Chat API, same key as Seedance (not Seedance video IDs).
    llm_provider: str = "byteplus"
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "seed-2-0-lite-260228"


@lru_cache
def get_settings() -> Settings:
    return Settings()
