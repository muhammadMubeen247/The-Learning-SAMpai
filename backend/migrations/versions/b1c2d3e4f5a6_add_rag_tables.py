"""Add RAG KV store, doc status tables, and rag_doc_id column on files

Revision ID: b1c2d3e4f5a6
Revises: a378ddb4c917
Create Date: 2026-04-08 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a378ddb4c917"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── rag_kv_store ────────────────────────────────────────────────────────
    # General-purpose JSONB key-value store for all LightRAG namespaces
    # (full_docs, text_chunks, llm_response_cache, full_entities,
    #  full_relations, entity_chunks, relation_chunks)
    op.create_table(
        "rag_kv_store",
        sa.Column("workspace", sa.VARCHAR(100), nullable=False),
        sa.Column("namespace", sa.VARCHAR(100), nullable=False),
        sa.Column("key", sa.VARCHAR(512), nullable=False),
        sa.Column("value", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("workspace", "namespace", "key"),
    )
    op.create_index(
        "idx_rag_kv_ws_ns",
        "rag_kv_store",
        ["workspace", "namespace"],
    )

    # ── rag_doc_status ─────────────────────────────────────────────────────
    # Per-document processing status, chunk list, and metadata
    op.create_table(
        "rag_doc_status",
        sa.Column("workspace", sa.VARCHAR(100), nullable=False),
        sa.Column("doc_id", sa.VARCHAR(512), nullable=False),
        sa.Column("status", sa.VARCHAR(50), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("chunks_count", sa.Integer(), nullable=True),
        sa.Column(
            "chunks_list",
            JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("workspace", "doc_id"),
    )
    op.create_index(
        "idx_rag_doc_status_ws",
        "rag_doc_status",
        ["workspace"],
    )
    op.create_index(
        "idx_rag_doc_status_fp",
        "rag_doc_status",
        ["file_path"],
    )

    # ── files.rag_doc_id ───────────────────────────────────────────────────
    # Links a File row to its LightRAG document ID (md5 hash of file_url)
    op.add_column(
        "files",
        sa.Column("rag_doc_id", sa.VARCHAR(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("files", "rag_doc_id")

    op.drop_index("idx_rag_doc_status_fp", table_name="rag_doc_status")
    op.drop_index("idx_rag_doc_status_ws", table_name="rag_doc_status")
    op.drop_table("rag_doc_status")

    op.drop_index("idx_rag_kv_ws_ns", table_name="rag_kv_store")
    op.drop_table("rag_kv_store")
