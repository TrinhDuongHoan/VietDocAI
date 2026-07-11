import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260711_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "documents" not in inspector.get_table_names():
        op.create_table(
            "documents",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("original_filename", sa.String(length=512), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("model_name", sa.String(length=100), nullable=True),
            sa.Column("model_version", sa.String(length=100), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector.clear_cache()
    indexes = {index["name"] for index in inspector.get_indexes("documents")}

    if "ix_documents_status" not in indexes:
        op.create_index(
            "ix_documents_status",
            "documents",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_table("documents")
