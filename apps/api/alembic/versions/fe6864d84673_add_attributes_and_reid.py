"""add_attributes_and_reid

Revision ID: fe6864d84673
Revises: 44d6cb9353df
Create Date: 2026-06-13 21:51:00.265038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

# revision identifiers, used by Alembic.
revision: str = 'fe6864d84673'
down_revision: Union[str, Sequence[str], None] = '44d6cb9353df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. Create identity_gallery table
    op.create_table('identity_gallery',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('object_type', sa.String(length=50), nullable=False),
        sa.Column('reid_embedding', pgvector.sqlalchemy.vector.VECTOR(dim=512), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_identity_gallery_object_type', 'identity_gallery', ['object_type'], unique=False)
    op.create_index('ix_identity_gallery_org_id', 'identity_gallery', ['org_id'], unique=False)

    # 2. Add columns to detected_objects table
    op.add_column('detected_objects', sa.Column('dominant_colour', sa.String(length=50), nullable=True))
    op.add_column('detected_objects', sa.Column('colour_confidence', sa.Double(), nullable=True))
    op.add_column('detected_objects', sa.Column('vehicle_type', sa.String(length=50), nullable=True))
    op.add_column('detected_objects', sa.Column('vehicle_type_confidence', sa.Double(), nullable=True))
    op.add_column('detected_objects', sa.Column('upper_colour', sa.String(length=50), nullable=True))
    op.add_column('detected_objects', sa.Column('upper_colour_conf', sa.Double(), nullable=True))
    op.add_column('detected_objects', sa.Column('lower_colour', sa.String(length=50), nullable=True))
    op.add_column('detected_objects', sa.Column('lower_colour_conf', sa.Double(), nullable=True))
    op.add_column('detected_objects', sa.Column('carried_items', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('detected_objects', sa.Column('gender_estimate', sa.String(length=50), nullable=True))
    op.add_column('detected_objects', sa.Column('gender_is_estimate', sa.Boolean(), nullable=True))
    op.add_column('detected_objects', sa.Column('attributes_extracted', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('detected_objects', sa.Column('reid_embedding', pgvector.sqlalchemy.vector.VECTOR(dim=512), nullable=True))
    op.add_column('detected_objects', sa.Column('gallery_id', sa.UUID(), nullable=True))
    
    op.create_index('ix_detected_objects_attributes_extracted', 'detected_objects', ['attributes_extracted'], unique=False)
    op.create_index('ix_detected_objects_gallery_id', 'detected_objects', ['gallery_id'], unique=False)
    
    # 3. Setup foreign key relationship
    op.create_foreign_key('fk_detected_objects_gallery_id', 'detected_objects', 'identity_gallery', ['gallery_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_detected_objects_gallery_id', 'detected_objects', type_='foreignkey')
    op.drop_index('ix_detected_objects_gallery_id', table_name='detected_objects')
    op.drop_index('ix_detected_objects_attributes_extracted', table_name='detected_objects')
    
    op.drop_column('detected_objects', 'gallery_id')
    op.drop_column('detected_objects', 'reid_embedding')
    op.drop_column('detected_objects', 'attributes_extracted')
    op.drop_column('detected_objects', 'gender_is_estimate')
    op.drop_column('detected_objects', 'gender_estimate')
    op.drop_column('detected_objects', 'carried_items')
    op.drop_column('detected_objects', 'lower_colour_conf')
    op.drop_column('detected_objects', 'lower_colour')
    op.drop_column('detected_objects', 'upper_colour_conf')
    op.drop_column('detected_objects', 'upper_colour')
    op.drop_column('detected_objects', 'vehicle_type_confidence')
    op.drop_column('detected_objects', 'vehicle_type')
    op.drop_column('detected_objects', 'colour_confidence')
    op.drop_column('detected_objects', 'dominant_colour')
    
    op.drop_index('ix_identity_gallery_org_id', table_name='identity_gallery')
    op.drop_index('ix_identity_gallery_object_type', table_name='identity_gallery')
    op.drop_table('identity_gallery')
