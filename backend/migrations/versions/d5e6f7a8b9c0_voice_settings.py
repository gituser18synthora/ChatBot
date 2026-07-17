"""TTS voice settings (platform + per-tenant)

Revision ID: d5e6f7a8b9c0
Revises: a9b7c6d5e4f3
Create Date: 2026-07-10 13:00:00.000000

One table for both levels: the tenant_id NULL row is the Super Admin's
platform defaults; per-tenant rows are Tenant Admin overrides (honored only
while the platform row's allow_tenant_override is true). Additive only.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'a9b7c6d5e4f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'voice_settings',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('tenant_id', sa.CHAR(length=36), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('provider', sa.String(length=40), nullable=False, server_default='browser'),
        sa.Column('voice_name', sa.String(length=200), nullable=True),
        sa.Column('language', sa.String(length=20), nullable=True),
        sa.Column('gender', sa.String(length=10), nullable=True),
        sa.Column('rate', sa.Float(), nullable=False, server_default='1'),
        sa.Column('pitch', sa.Float(), nullable=False, server_default='1'),
        sa.Column('volume', sa.Float(), nullable=False, server_default='1'),
        sa.Column('auto_play', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('allow_tenant_override', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('updated_by', sa.CHAR(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Model declares tenant_id as unique=True + index=True, which SQLAlchemy
    # realizes as a single UNIQUE index (not a separate constraint + index).
    op.create_index('ix_voice_settings_tenant_id', 'voice_settings', ['tenant_id'], unique=True)


def downgrade():
    op.drop_index('ix_voice_settings_tenant_id', table_name='voice_settings')
    op.drop_table('voice_settings')
