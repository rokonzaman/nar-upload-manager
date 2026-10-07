"""add deploy_environments to users

Revision ID: f34b5e40ea20
Revises: 113bcbf4115b
Create Date: 2026-09-17 18:24:24.239302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f34b5e40ea20"
down_revision: Union[str, None] = "113bcbf4115b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deploy_environments", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("deploy_environments")
