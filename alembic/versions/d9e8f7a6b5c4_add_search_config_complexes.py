"""add search_config_complexes

Revision ID: d9e8f7a6b5c4
Revises: a1b2c3d4e5f6
Create Date: 2026-07-14 10:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_config_complexes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("search_config_id", sa.Integer(), nullable=False),
        sa.Column("krisha_complex_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["search_config_id"],
            ["search_configs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "search_config_id",
            "krisha_complex_id",
            name="uq_search_config_complexes_config_krisha_id",
        ),
    )
    op.create_index(
        "ix_search_config_complexes_search_config_id",
        "search_config_complexes",
        ["search_config_id"],
        unique=False,
    )

    # Migrate legacy single complex_id into the new table.
    op.execute(
        """
        INSERT INTO search_config_complexes (search_config_id, krisha_complex_id, name)
        SELECT id, TRIM(complex_id), NULL
        FROM search_configs
        WHERE complex_id IS NOT NULL AND TRIM(complex_id) <> ''
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_search_config_complexes_search_config_id",
        table_name="search_config_complexes",
    )
    op.drop_table("search_config_complexes")
