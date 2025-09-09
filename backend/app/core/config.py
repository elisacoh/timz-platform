# backend/app/core/config.py
import os
from pathlib import Path

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

    # DB
    DATABASE_URL: str | None = None
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # 3rd parties (optional now)
    STRIPE_SECRET: str | None = None
    SENDGRID_API_KEY: str | None = None

    # Firebase Admin credentials (choose one)
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    FIREBASE_CREDENTIALS_B64: str | None = None  # base64 of JSON content

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
