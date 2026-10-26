"""Wiederkehrende Rechnungen

Revision ID: a2c5e8f1b749
Revises: f7b2d4c8a613
Create Date: 2026-10-26 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2c5e8f1b749'
down_revision = 'f7b2d4c8a613'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wiederkehrende_rechnung',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('kontakt_id', sa.Integer(), nullable=True),
        sa.Column('empfaenger_name', sa.String(length=200), nullable=True),
        sa.Column('empfaenger_zusatz', sa.String(length=200), nullable=True),
        sa.Column('empfaenger_strasse', sa.String(length=200), nullable=True),
        sa.Column('empfaenger_plz', sa.String(length=10), nullable=True),
        sa.Column('empfaenger_ort', sa.String(length=100), nullable=True),
        sa.Column('empfaenger_land', sa.String(length=100), nullable=True),
        sa.Column('titel', sa.String(length=100), nullable=False),
        sa.Column('einleitung', sa.Text(), nullable=True),
        sa.Column('nachbemerkung', sa.Text(), nullable=True),
        sa.Column('hinweis_steuerbefreiung', sa.Text(), nullable=True),
        sa.Column('zahlungsziel_tage', sa.Integer(), nullable=False),
        sa.Column('qr_ueberweisung', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('summe_cent', sa.BigInteger(), nullable=False),
        sa.Column('intervall', sa.String(length=20), nullable=False),
        sa.Column('anker_tag', sa.Integer(), nullable=False),
        sa.Column('naechste_am', sa.Date(), nullable=False),
        sa.Column('ende_am', sa.Date(), nullable=True),
        sa.Column('aktiv', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('versand', sa.String(length=20), server_default='entwurf', nullable=False),
        sa.Column('erzeugt_anzahl', sa.Integer(), server_default='0', nullable=False),
        sa.Column('letzter_lauf_am', sa.DateTime(timezone=True), nullable=True),
        sa.Column('letzte_meldung', sa.Text(), nullable=True),
        sa.Column('erstellt_von', sa.Integer(), nullable=False),
        sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("intervall IN ('monatlich', 'quartalsweise', 'halbjaehrlich', 'jaehrlich')", name='wiederkehrend_intervall'),
        sa.CheckConstraint("versand IN ('entwurf', 'festschreiben', 'senden')", name='wiederkehrend_versand'),
        sa.CheckConstraint('anker_tag BETWEEN 1 AND 31', name='wiederkehrend_anker'),
        sa.ForeignKeyConstraint(['erstellt_von'], ['nutzer.id']),
        sa.ForeignKeyConstraint(['kontakt_id'], ['kontakt.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'wiederkehrende_position',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vorlage_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('typ', sa.String(length=10), nullable=False),
        sa.Column('artikel_id', sa.Integer(), nullable=True),
        sa.Column('bezeichnung', sa.String(length=200), nullable=False),
        sa.Column('beschreibung', sa.Text(), nullable=True),
        sa.Column('menge_tausendstel', sa.BigInteger(), nullable=False),
        sa.Column('einheit', sa.String(length=30), nullable=True),
        sa.Column('einzelpreis_cent', sa.BigInteger(), nullable=False),
        sa.Column('rabatt_bp', sa.Integer(), nullable=False),
        sa.Column('betrag_cent', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("typ IN ('artikel', 'text')", name='wiederkehrend_position_typ'),
        sa.CheckConstraint('rabatt_bp BETWEEN 0 AND 10000', name='wiederkehrend_position_rabatt'),
        sa.ForeignKeyConstraint(['artikel_id'], ['artikel.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vorlage_id'], ['wiederkehrende_rechnung.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('rechnung', sa.Column('wiederkehrend_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'rechnung_wiederkehrend_id_fkey', 'rechnung', 'wiederkehrende_rechnung',
        ['wiederkehrend_id'], ['id'], ondelete='RESTRICT',
    )


def downgrade():
    op.drop_constraint('rechnung_wiederkehrend_id_fkey', 'rechnung', type_='foreignkey')
    op.drop_column('rechnung', 'wiederkehrend_id')
    op.drop_table('wiederkehrende_position')
    op.drop_table('wiederkehrende_rechnung')
