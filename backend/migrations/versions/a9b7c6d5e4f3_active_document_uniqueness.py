"""active document uniqueness

Revision ID: a9b7c6d5e4f3
Revises: f2c9a0b1d2e3
Create Date: 2026-07-09 11:05:00.000000

Guarantees a single active document row per tenant + KB + filename while
preserving duplicate history as soft-deleted rows.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9b7c6d5e4f3'
down_revision = 'f2c9a0b1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('active_file_key', sa.String(length=500), nullable=True))

    op.execute("""
        UPDATE documents
        SET active_file_key = original_filename
        WHERE upload_status <> 'deleted'
          AND deleted_at IS NULL
    """)

    # Keep one visible row per tenant/kb/file. Prefer indexed rows, then active
    # processing rows, then retryable failed/pending rows; preserve the rest as
    # soft-deleted history so UI/chat/query paths no longer see duplicates.
    op.execute("""
        UPDATE documents
        SET upload_status = 'deleted',
            deleted_at = CURRENT_TIMESTAMP,
            active_file_key = NULL,
            ingestion_error = 'Duplicate document record superseded during active-file cleanup.'
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY tenant_id, kb_id, active_file_key
                        ORDER BY
                            CASE upload_status
                                WHEN 'completed' THEN 1
                                WHEN 'processing' THEN 2
                                WHEN 'uploading' THEN 3
                                WHEN 'pending' THEN 4
                                WHEN 'failed' THEN 5
                                ELSE 6
                            END,
                            COALESCE(processed_at, uploaded_at, created_at) DESC,
                            id DESC
                    ) AS row_rank
                FROM documents
                WHERE active_file_key IS NOT NULL
            ) ranked_documents
            WHERE row_rank > 1
        )
    """)

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_documents_active_file',
            ['tenant_id', 'kb_id', 'active_file_key'],
        )

    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_knowledge_bases_tenant_id_id',
            ['tenant_id', 'id'],
        )


def downgrade():
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.drop_constraint('uq_knowledge_bases_tenant_id_id', type_='unique')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('uq_documents_active_file', type_='unique')
        batch_op.drop_column('active_file_key')
