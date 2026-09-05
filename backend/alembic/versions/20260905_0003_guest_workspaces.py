"""Add anonymous guest ownership to workspace records.

Revision ID: 20260905_0003
Revises: 20260903_0002
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260905_0003"
down_revision: Union[str, None] = "20260903_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("projects", "workflows", "conversations"):
        op.add_column(table_name, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.create_index(
            f"ix_{table_name}_owner_id", table_name, ["owner_id"], unique=False
        )


def downgrade() -> None:
    for table_name in ("conversations", "workflows", "projects"):
        op.drop_index(f"ix_{table_name}_owner_id", table_name=table_name)
        op.drop_column(table_name, "owner_id")
