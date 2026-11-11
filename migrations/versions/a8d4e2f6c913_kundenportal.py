"""Kundenportal: Links für Kunden, Einstellungen

Revision ID: a8d4e2f6c913
Revises: c5e9a3d7b214
Create Date: 2026-11-11 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8d4e2f6c913'
down_revision = 'c5e9a3d7b214'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gewerbe', sa.Column('kundenportal', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('gewerbe', sa.Column('kundenportal_plz', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('gewerbe', sa.Column('oeffentliche_adresse', sa.String(length=300), nullable=True))
    op.create_table(
        'kundenlink',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rechnung_id', sa.Integer(), nullable=False),
        sa.Column('schluessel_hash', sa.String(length=64), nullable=False),
        sa.Column('schluessel_geheim', sa.Text(), nullable=False),
        sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('gesperrt_am', sa.DateTime(timezone=True), nullable=True),
        sa.Column('abrufe', sa.Integer(), server_default='0', nullable=False),
        sa.Column('zuletzt_abgerufen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fehlversuche', sa.Integer(), server_default='0', nullable=False),
        sa.Column('gesperrt_bis', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entschieden_am', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entschieden_von', sa.String(length=200), nullable=True),
        sa.Column('kommentar', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rechnung_id'], ['rechnung.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('schluessel_hash'),
    )
    op.create_index('ix_kundenlink_rechnung_id', 'kundenlink', ['rechnung_id'])


def downgrade():
    op.drop_index('ix_kundenlink_rechnung_id', table_name='kundenlink')
    op.drop_table('kundenlink')
    op.drop_column('gewerbe', 'oeffentliche_adresse')
    op.drop_column('gewerbe', 'kundenportal_plz')
    op.drop_column('gewerbe', 'kundenportal')
