"""enterprise auth sessions and refresh rotation

Revision ID: f9a8b7c6d5e4
Revises: e3f4a5b6c7d8
Create Date: 2026-07-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f9a8b7c6d5e4'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(), nullable=True))

    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('user_id', sa.CHAR(length=36), nullable=False),
        sa.Column('device_id', sa.String(length=80), nullable=False),
        sa.Column('user_agent', sa.String(length=400), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_reason', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_sessions_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_sessions')),
    )
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_sessions_device_id'), ['device_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_sessions_revoked_at'), ['revoked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_sessions_user_id'), ['user_id'], unique=False)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('session_id', sa.CHAR(length=36), nullable=False),
        sa.Column('user_id', sa.CHAR(length=36), nullable=False),
        sa.Column('family_id', sa.CHAR(length=36), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('jti_hash', sa.String(length=128), nullable=False),
        sa.Column('parent_jti_hash', sa.String(length=128), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_reason', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['auth_sessions.id'], name=op.f('fk_refresh_tokens_session_id_auth_sessions'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_family_id'), ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_jti_hash'), ['jti_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_parent_jti_hash'), ['parent_jti_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_revoked_at'), ['revoked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_session_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_revoked_at'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_parent_jti_hash'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_jti_hash'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_family_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_expires_at'))
    op.drop_table('refresh_tokens')

    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_revoked_at'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_expires_at'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_device_id'))
    op.drop_table('auth_sessions')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_count')
