"""Passkeys (WebAuthn)

Revision ID: b3d7f1a9c825
Revises: a2c5e8f1b749
Create Date: 2026-10-26 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b3d7f1a9c825'
down_revision = 'a2c5e8f1b749'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'passkey',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nutzer_id', sa.Integer(), nullable=False),
        sa.Column('credential_id', sa.LargeBinary(), nullable=False),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('transports', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('geraetetyp', sa.String(length=20), nullable=False),
        sa.Column('gesichert', sa.Boolean(), nullable=False),
        sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('zuletzt_benutzt_am', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['nutzer_id'], ['nutzer.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credential_id'),
    )
    op.create_index('ix_passkey_nutzer_id', 'passkey', ['nutzer_id'])


def downgrade():
    op.drop_index('ix_passkey_nutzer_id', table_name='passkey')
    op.drop_table('passkey')
