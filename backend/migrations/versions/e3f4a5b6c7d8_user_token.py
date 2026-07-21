"""chat user access tokens

Revision ID: e3f4a5b6c7d8
Revises: a1f2e3d4c5b6
Create Date: 2026-07-21

Adds `user_token`: one row per Chat User holding the generated access token
plus the tenant_id / kb_ids / user_id snapshot used to issue it.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'a1f2e3d4c5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_token',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('user_id', sa.CHAR(length=36), nullable=False),
        sa.Column('tenant_id', sa.CHAR(length=36), nullable=False),
        sa.Column('kb_ids', sa.JSON(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('created_by', sa.CHAR(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_token_user_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_user_token_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_token')),
        sa.UniqueConstraint('user_id', name='uq_user_token_user_id'),
        sa.UniqueConstraint('token', name='uq_user_token_token'),
    )
    with op.batch_alter_table('user_token', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_token_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_token_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_token_token'), ['token'], unique=False)


def downgrade():
    with op.batch_alter_table('user_token', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_token_token'))
        batch_op.drop_index(batch_op.f('ix_user_token_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_user_token_user_id'))
    op.drop_table('user_token')
