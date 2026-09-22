"""Application configuration with environment variable loading and SQLite fallback."""

from typing import List, Union, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    RATE_LIMIT_ENABLED: bool = True

    # Supabase Configuration
    SUPABASE_URL: str = "https://placeholder-project.supabase.co"
    SUPABASE_ANON_KEY: str = "placeholder-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: str = "placeholder-service-role-key-32bytes-minimum"
    SUPABASE_JWT_SECRET: str = "sentinel-super-secret-jwt-key-32bytes-for-development-mode-auth-2026"

    # Database URL with SQLite fallback for pure-local development
    DATABASE_URL: str = "sqlite:///./cryptotrace_dev.db"

    # Golden Hour Watchlist & Webhook Configuration
    ENABLE_TELEGRAM_WEBHOOK: bool = False
    TELEGRAM_BOT_TOKEN: str = "stub-telegram-bot-token"
    TELEGRAM_CHAT_ID: str = "stub-chat-id"
    WATCHLIST_POLL_INTERVAL_SECONDS: int = 15

    # AI Co-pilot (Arjuna) Configuration
    GEMINI_API_KEY: str = ""

    # Phase 9: Guarded LLM Complaint Intake Configuration
    LLM_PROVIDER: str = "none"  # "none", "anthropic", "ollama"
    LLM_MODEL: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OLLAMA_URL: str = "http://localhost:11434"

    # Phase 8: Multi-Chain Live Provider Configuration (Defaults to FixtureAdapter if LIVE_MODE=False)

    LIVE_MODE: bool = False
    EVM_RPC_URL: Optional[str] = None
    ETH_RPC_URL: Optional[str] = None  # Alias for EVM_RPC_URL
    ETHERSCAN_API_KEY: Optional[str] = None
    TRON_RPC_URL: Optional[str] = "https://api.trongrid.io"
    TRONGRID_API_KEY: Optional[str] = None
    MEMPOOL_API_URL: str = "https://mempool.space/api"
    CONFIRMATION_THRESHOLD: int = 3
    CACHE_TTL_PENDING: int = 20    # 20 seconds for pending/low-confirmation
    CACHE_TTL_SETTLED: int = 300   # 5 minutes for settled/finalized txs

    # Phase 8E: GraphSense TagPacks & Live Entity API Configuration
    GRAPHSENSE_API_URL: str = "https://api.ikna.io"
    GRAPHSENSE_API_KEY: Optional[str] = None
    TAGPACK_REFRESH_INTERVAL_DAYS: int = 7

    # CORS Origins (comma-separated string or list)
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
