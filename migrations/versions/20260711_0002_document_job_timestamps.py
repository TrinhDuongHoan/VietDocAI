import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260711_0002"
down_revision = "20260711_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns("documents")
    }

    if "processing_started_at" not in columns:
        op.add_column(
            "documents",
            sa.Column(
                "processing_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if "completed_at" not in columns:
        op.add_column(
            "documents",
            sa.Column(
                "completed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if "failed_at" not in columns:
        op.add_column(
            "documents",
            sa.Column(
                "failed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("documents", "failed_at")
    op.drop_column("documents", "completed_at")
    op.drop_column("documents", "processing_started_at")
