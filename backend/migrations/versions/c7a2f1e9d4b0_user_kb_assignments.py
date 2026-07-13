"""per-user knowledge base assignments

Revision ID: c7a2f1e9d4b0
Revises: b1e743cb2336
Create Date: 2026-07-08 11:00:00.000000

Adds `user_knowledge_base_assignments`, which scopes an individual user's chat
retrieval to a chosen subset of Knowledge Bases. A user with no rows here uses
all of their tenant's accessible KBs (the default); rows here restrict them to
exactly those KBs. Additive only — existing data is untouched.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c7a2f1e9d4b0'
down_revision = 'b1e743cb2336'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_knowledge_base_assignments',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('user_id', sa.CHAR(length=36), nullable=False),
        sa.Column('kb_id', sa.CHAR(length=36), nullable=False),
        sa.Column('assigned_by', sa.CHAR(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_knowledge_base_assignments_user_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], name=op.f('fk_user_knowledge_base_assignments_kb_id_knowledge_bases'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_knowledge_base_assignments')),
        sa.UniqueConstraint('user_id', 'kb_id', name='uq_user_kb_assignment'),
    )
    with op.batch_alter_table('user_knowledge_base_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_knowledge_base_assignments_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_knowledge_base_assignments_kb_id'), ['kb_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_knowledge_base_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_knowledge_base_assignments_kb_id'))
        batch_op.drop_index(batch_op.f('ix_user_knowledge_base_assignments_user_id'))
    op.drop_table('user_knowledge_base_assignments')
