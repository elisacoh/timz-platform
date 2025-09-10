# backend/timz_app/core/config.py
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # .../backend
load_dotenv(BASE_DIR / ".env", override=True)


class Settings(BaseSettings):

    # App basics
    ENV: str = "dev"
    TZ: str = "Asia/Jerusalem"

    # Security / Auth
    JWT_SECRET: str | None = None
    JWT_ALG: str = "HS256"
    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 30
    REFRESH_TOKEN_PEPPER: str

    # DB
    DATABASE_URL: str | None = None
    # model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # 3rd parties (optional now)
    STRIPE_SECRET: str | None = None
    SENDGRID_API_KEY: str | None = None

    # Firebase
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None  # dev
    FIREBASE_CREDENTIALS_B64: str | None = None  # base64 of JSON content PROD
    FIREBASE_PROJECT_ID: str
    FIREBASE_ISSUER: Optional[str] = None
    FIREBASE_AUDIENCE: Optional[str] = None

    APP_ENV: str = "dev"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def firebase_issuer_effective(self) -> str:
        return (
            self.FIREBASE_ISSUER
            or f"https://securetoken.google.com/{self.FIREBASE_PROJECT_ID}"
        )

    @property
    def firebase_audience_effective(self) -> str:
        return self.FIREBASE_AUDIENCE or self.FIREBASE_PROJECT_ID


settings = Settings()
