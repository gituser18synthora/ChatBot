"""knowledge base readiness status

Revision ID: f2c9a0b1d2e3
Revises: e8b1c2d3f4a5
Create Date: 2026-07-09 08:45:00.000000

Adds a lifecycle message for Knowledge Bases and migrates the old coarse
`active` state to derived readiness states. A KB is chat-ready only after at
least one document is confirmed indexed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c9a0b1d2e3'
down_revision = 'e8b1c2d3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status_message', sa.Text(), nullable=True))

    op.execute("""
        UPDATE knowledge_bases
        SET status = 'ready',
            status_message = 'Knowledge Base is ready for chat.'
        WHERE status = 'active'
          AND EXISTS (
            SELECT 1 FROM documents d
            WHERE d.kb_id = knowledge_bases.id
              AND d.upload_status = 'completed'
          )
    """)
    op.execute("""
        UPDATE knowledge_bases
        SET status = 'processing',
            status_message = 'Document indexing is pending.'
        WHERE status = 'active'
          AND EXISTS (
            SELECT 1 FROM documents d
            WHERE d.kb_id = knowledge_bases.id
              AND d.upload_status IN ('pending', 'uploading', 'processing')
          )
    """)
    op.execute("""
        UPDATE knowledge_bases
        SET status = 'failed',
            status_message = 'Knowledge Base creation failed. Retry failed documents after KMRAG is available.'
        WHERE status = 'active'
          AND EXISTS (
            SELECT 1 FROM documents d
            WHERE d.kb_id = knowledge_bases.id
              AND d.upload_status = 'failed'
          )
    """)
    op.execute("""
        UPDATE knowledge_bases
        SET status = 'pending',
            status_message = 'Upload documents to start indexing this Knowledge Base.'
        WHERE status = 'active'
    """)
    op.execute("""
        UPDATE knowledge_bases
        SET status_message = 'Knowledge Base is inactive.'
        WHERE status = 'inactive'
          AND status_message IS NULL
    """)


def downgrade():
    op.execute("""
        UPDATE knowledge_bases
        SET status = 'active'
        WHERE status IN ('pending', 'processing', 'ready', 'failed')
    """)
    with op.batch_alter_table('knowledge_bases', schema=None) as batch_op:
        batch_op.drop_column('status_message')
