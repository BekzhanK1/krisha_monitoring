"""add_apartment_scores

Revision ID: c8f2a1b3d4e5
Revises: 556673d599e2
Create Date: 2026-06-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8f2a1b3d4e5"
down_revision: Union[str, Sequence[str], None] = "556673d599e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "apartment_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apartment_id", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("roi_pct", sa.Float(), nullable=False),
        sa.Column("owner_probability", sa.Float(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["apartment_id"], ["apartments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apartment_id"),
    )
    op.create_index(
        "ix_apartment_scores_apartment_id",
        "apartment_scores",
        ["apartment_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_apartment_scores_apartment_id", table_name="apartment_scores")
    op.drop_table("apartment_scores")
