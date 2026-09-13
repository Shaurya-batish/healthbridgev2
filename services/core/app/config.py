from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://healthbridge:healthbridge@localhost:5432/healthbridge"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12
    port: int = 8000

    # --- ABDM Gateway (HIP-side) -- see docs/REAL-INTEGRATION-AUDIT.md ---
    # Unset by default: real values are issued only after NHA HIP
    # registration/certification, which is an external process this
    # environment cannot complete. Never hardcode these -- env vars only.
    abdm_gateway_base_url: str | None = None
    abdm_client_id: str | None = None
    abdm_client_secret: str | None = None
    abdm_hip_id: str | None = None
    abdm_cm_id: str = "sbx"

    # --- PM-JAY / state scheme verification (NHA Beneficiary Identification
    # System) -- also gated on real NHA empanelment credentials ---
    nha_beneficiary_base_url: str | None = None
    nha_operator_username: str | None = None
    nha_operator_password: str | None = None

    # --- Teleconsult store-and-forward media (self-hosted, no external dep) ---
    teleconsult_media_dir: str = "./data/teleconsult-media"


@lru_cache
def get_settings() -> Settings:
    return Settings()
