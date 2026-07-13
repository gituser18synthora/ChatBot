"""per-tenant RAG answering mode

Revision ID: e8b1c2d3f4a5
Revises: c7a2f1e9d4b0
Create Date: 2026-07-09 06:00:00.000000

Adds `tenants.rag_mode`: 'rag_first' (default — document questions answered from
the tenant's KBs, clearly general questions may use general AI) or 'rag_only'
(general AI fallback disabled; the bot only answers from Knowledge Bases).
Additive only — existing tenants get the default.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e8b1c2d3f4a5'
down_revision = 'c7a2f1e9d4b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('rag_mode', sa.String(length=20), nullable=False,
                      server_default='rag_first')
        )


def downgrade():
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('rag_mode')
