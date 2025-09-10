from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "XXXXXXXX"          # <-- laissé tel quel par Alembic
down_revision: Union[str, Sequence[str], None] = "c34c3fdcf85a"  # ta baseline
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=False)  # (facultatif si tu voulais juste index=True)


def downgrade() -> None:
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
