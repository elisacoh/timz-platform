"""seed roles

Revision ID: 6e2a1696a52d
Revises: 9eb72d20b92f
Create Date: 2025-09-10 10:44:29.579052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e2a1696a52d'
down_revision: Union[str, Sequence[str], None] = '9eb72d20b92f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Variante SQL (simple et robuste, évite les doublons si relancé)
    op.execute("""
        INSERT INTO roles (name)
        VALUES ('client'), ('pro'), ('admin')
        ON CONFLICT (name) DO NOTHING;
    """)

    # Si tu préfères SQLAlchemy, tu peux utiliser op.bulk_insert :
    # roles = sa.table("roles", sa.column("name", sa.String))
    # op.bulk_insert(roles, [{"name": "client"}, {"name": "pro"}, {"name": "admin"}])


def downgrade() -> None:
    # Nettoyage si on rollback
    op.execute("DELETE FROM roles WHERE name IN ('client','pro','admin');")