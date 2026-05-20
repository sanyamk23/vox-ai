import os
import re
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://vox_user:vox_pass@db:5432/vox_db"
    REDIS_URL: str = "redis://redis:6379/0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: str = "*"

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    PUBLIC_URL: str = ""
    VOX_API_KEY: str = ""

    GEMINI_API_KEY: str = ""
    GEMINI_SUMMARY_MODEL: str = "gemini-2.0-flash"

    SENTRY_DSN: str = ""

    def async_db_url(self) -> str:
        """Convert postgres(ql):// → postgresql+asyncpg:// for SQLAlchemy async."""
        return re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", self.DATABASE_URL)

    def allowed_origins_list(self) -> list[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
