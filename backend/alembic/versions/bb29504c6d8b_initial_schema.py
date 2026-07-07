"""initial_schema

Revision ID: bb29504c6d8b
Revises: 
Create Date: 2026-07-07 21:38:29.557758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb29504c6d8b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # events table
    op.create_table('events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('event_id')
    )
    op.create_index(op.f('ix_events_event_id'), 'events', ['event_id'], unique=False)
    op.create_index('ix_events_tenant_created_at', 'events', ['tenant_id', 'created_at'], unique=False)
    op.create_index('ix_events_tenant_timestamp', 'events', ['tenant_id', 'timestamp'], unique=False)

    # aggregates table
    op.create_table('aggregates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('bucket_size', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'bucket_start', 'bucket_size', 'source', 'event_type', name='uq_aggregate_dimensions')
    )

    # aggregation_state table
    op.create_table('aggregation_state',
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('last_processed_created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('tenant_id')
    )
    op.create_index(op.f('ix_aggregation_state_tenant_id'), 'aggregation_state', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_aggregation_state_tenant_id'), table_name='aggregation_state')
    op.drop_table('aggregation_state')
    op.drop_table('aggregates')
    op.drop_index('ix_events_tenant_timestamp', table_name='events')
    op.drop_index('ix_events_tenant_created_at', table_name='events')
    op.drop_index(op.f('ix_events_event_id'), table_name='events')
    op.drop_table('events')
