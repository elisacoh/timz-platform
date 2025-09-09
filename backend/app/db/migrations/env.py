import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url

from app.core.config import settings
# Modèles
from app.db.base import Base

# Chemin .../backend
BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Charge explicitement backend/.env (pour Alembic lancé depuis n'importe où)
load_dotenv(BASE_DIR / ".env", override=True)

config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def set_sync_sqlalchemy_url_from_env():
    # Ne calcule l'URL depuis .env que si alembic.ini n'en fournit pas déjà une
    if config.get_main_option("sqlalchemy.url"):
        # alembic.ini a priorité → ne rien faire
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
