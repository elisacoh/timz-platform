# backend/timz_app/db/migrations/env.py

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url

# ---- Positionne le sys.path AVANT tout import timz_app.*
BASE_DIR = Path(__file__).resolve().parents[3]  # .../backend
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Charge .env ici, avant d'importer settings
load_dotenv(BASE_DIR / ".env", override=True)

# Maintenant on peut importer la config et Base
from timz_app.core.config import settings
from timz_app.db.base import Base

# Alembic config & logging
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- Importe explicitement TOUS les modèles pour peupler Base.metadata
import timz_app.db.base_models  # noqa: F401

target_metadata = Base.metadata
print("Alembic sqlalchemy.url =", context.config.get_main_option("sqlalchemy.url"))
print("Models loaded (tables) =", list(target_metadata.tables.keys()))


def set_sync_sqlalchemy_url_from_env():
    # Si alembic.ini fournit déjà sqlalchemy.url, on ne touche pas
    if config.get_main_option("sqlalchemy.url"):
        return

    url_str = settings.DATABASE_URL or os.getenv("DATABASE_URL")
    if not url_str:
        return

    url = make_url(url_str)
    if "asyncpg" in url.drivername:
        url = url.set(drivername="postgresql+psycopg")
    config.set_main_option("sqlalchemy.url", str(url))
    print("Alembic sqlalchemy.url =", config.get_main_option("sqlalchemy.url"))


set_sync_sqlalchemy_url_from_env()


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
