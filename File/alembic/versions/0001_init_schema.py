
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_init_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='viewer')
    )

    op.create_table('audits',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('site_url', sa.Text(), nullable=False),
        sa.Column('overall_score', sa.Integer(), nullable=False),
        sa.Column('grade', sa.String(length=3), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()) if op.get_bind().dialect.name == 'postgresql' else sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True)
    )
    op.create_index('ix_audits_user_id', 'audits', ['user_id'])

    op.create_table('audit_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('audit_id', sa.String(length=36), sa.ForeignKey('audits.id'), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Integer(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.Column('impact', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False)
    )
    op.create_unique_constraint('uq_audit_category_code', 'audit_metrics', ['audit_id', 'category', 'code'])
    op.create_index('ix_audit_metrics_audit_id', 'audit_metrics', ['audit_id'])

    op.create_table('magic_link_tokens',
        sa.Column('token', sa.String(length=64), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('redeemed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False)
    )

def downgrade():
    op.drop_table('magic_link_tokens')
    op.drop_index('ix_audit_metrics_audit_id', table_name='audit_metrics')
    op.drop_constraint('uq_audit_category_code', 'audit_metrics', type_='unique')
    op.drop_table('audit_metrics')
    op.drop_index('ix_audits_user_id', table_name='audits')
    op.drop_table('audits')
    op.drop_table('users')
