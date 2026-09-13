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
    # Comma-separated list. Core is only ever meant to be called
    # server-to-server by the Next.js gateway (architecture: "both clients
    # talk only to the gateway") -- CORS only matters at all if a browser
    # tries to hit Core's published port directly, and a wildcard there
    # served no purpose except widening the attack surface once auth was
    # added. Default matches the documented local dev gateway origin.
    core_allowed_origins: str = "http://localhost:3000"

    @property
    def core_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.core_allowed_origins.split(",") if origin.strip()]

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
    # Caps the in-memory read in upload_teleconsult_media -- without this,
    # an arbitrarily large upload gets read fully into memory before any
    # size check, which is a real memory-exhaustion DoS vector. 25MB is
    # generous for a voice/video note recorded on a low-end phone.
    teleconsult_max_upload_bytes: int = 25 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
