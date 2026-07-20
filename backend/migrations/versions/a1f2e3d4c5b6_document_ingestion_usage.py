"""document ingestion token/cost totals

Revision ID: a1f2e3d4c5b6
Revises: d5e6f7a8b9c0
Create Date: 2026-07-17

Stores KMRAG's per-file ingestion totals (embedding + OCR + LLM structuring) on
the document row. NULL ingestion_total_tokens means "not billed yet" and is what
makes usage capture idempotent.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1f2e3d4c5b6'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('ingestion_total_tokens', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('ingestion_cost_usd', sa.Numeric(16, 10), nullable=True))


def downgrade():
    op.drop_column('documents', 'ingestion_cost_usd')
    op.drop_column('documents', 'ingestion_total_tokens')
