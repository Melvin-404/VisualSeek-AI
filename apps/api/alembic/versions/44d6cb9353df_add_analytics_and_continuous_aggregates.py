"""add_analytics_and_continuous_aggregates

Revision ID: 44d6cb9353df
Revises: a7b134d4f0fe
Create Date: 2026-06-11 16:34:10.000296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44d6cb9353df'
down_revision: Union[str, Sequence[str], None] = 'a7b134d4f0fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
disable_ddl_transaction: bool = True


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Modify composite PK for search_queries (but skip hypertable)
    try:
        # Drop existing PK constraint
        op.execute("ALTER TABLE search_queries DROP CONSTRAINT IF EXISTS search_queries_pkey CASCADE;")
        # Add composite PK (id, created_at)
        op.execute("ALTER TABLE search_queries ADD PRIMARY KEY (id, created_at);")
    except Exception:
        pass

    # 2. Modify composite PK for detected_objects (but skip hypertable)
    try:
        # Drop existing PK constraint
        op.execute("ALTER TABLE detected_objects DROP CONSTRAINT IF EXISTS detected_objects_pkey CASCADE;")
        # Add composite PK (id, created_at)
        op.execute("ALTER TABLE detected_objects ADD PRIMARY KEY (id, created_at);")
    except Exception:
        pass

    # 3. Create camera_health_logs table
    if 'camera_health_logs' not in tables:
        op.create_table(
            'camera_health_logs',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('org_id', sa.UUID(), nullable=False),
            sa.Column('camera_id', sa.UUID(), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Column('uptime_status', sa.String(length=50), nullable=False),
            sa.Column('frame_drop_rate', sa.Double(), nullable=False),
            sa.Column('detection_latency_ms', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', 'timestamp')
        )
        op.create_index('ix_camera_health_org_id', 'camera_health_logs', ['org_id'], unique=False)
        op.create_index('ix_camera_health_timestamp_brin', 'camera_health_logs', ['timestamp'], unique=False, postgresql_using='brin')

        # Enable RLS on camera_health_logs
        op.execute("ALTER TABLE camera_health_logs ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE camera_health_logs FORCE ROW LEVEL SECURITY;")
        op.execute("""
        CREATE POLICY org_isolation ON camera_health_logs
        FOR ALL
        USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        # Grant privileges to application role
        op.execute("GRANT ALL PRIVILEGES ON TABLE camera_health_logs TO visionquery_app;")

    # Get the raw psycopg connection and set autocommit
    bind = op.get_bind()
    raw_conn = bind.connection.dbapi_connection
    raw_conn.commit()
    old_autocommit = raw_conn.autocommit
    raw_conn.autocommit = True
    cursor = raw_conn.cursor()

    try:
        # Drop existing views/materialized views first to ensure we can recreate them clean
        cursor.execute("DROP VIEW IF EXISTS events_hourly CASCADE;")
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS events_hourly CASCADE;")
        cursor.execute("DROP VIEW IF EXISTS search_queries_hourly CASCADE;")
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS search_queries_hourly CASCADE;")
        cursor.execute("DROP VIEW IF EXISTS detections_daily CASCADE;")
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS detections_daily CASCADE;")
        cursor.execute("DROP VIEW IF EXISTS camera_health_hourly CASCADE;")
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS camera_health_hourly CASCADE;")

        # 4. Create Standard Views instead of TimescaleDB Continuous Aggregates
        # Events hourly aggregate view
        cursor.execute("""
        CREATE OR REPLACE VIEW events_hourly AS
        SELECT
            date_trunc('hour', start_time) AS bucket,
            org_id,
            camera_id,
            event_type,
            severity,
            COUNT(*) AS event_count
        FROM events
        GROUP BY bucket, org_id, camera_id, event_type, severity;
        """)

        # Search queries hourly aggregate view
        cursor.execute("""
        CREATE OR REPLACE VIEW search_queries_hourly AS
        SELECT
            date_trunc('hour', created_at) AS bucket,
            org_id,
            COUNT(*) AS query_count,
            AVG(latency_ms) AS avg_latency_ms,
            COUNT(CASE WHEN results_count = 0 THEN 1 END) AS zero_results_count
        FROM search_queries
        GROUP BY bucket, org_id;
        """)

        # Detected objects daily aggregate view
        cursor.execute("""
        CREATE OR REPLACE VIEW detections_daily AS
        SELECT
            date_trunc('day', created_at) AS bucket,
            org_id,
            class_label,
            COUNT(*) AS object_count
        FROM detected_objects
        GROUP BY bucket, org_id, class_label;
        """)

        # Camera health hourly aggregate view
        cursor.execute("""
        CREATE OR REPLACE VIEW camera_health_hourly AS
        SELECT
            date_trunc('hour', timestamp) AS bucket,
            org_id,
            camera_id,
            AVG(CASE WHEN uptime_status = 'online' THEN 1.0 ELSE 0.0 END) AS uptime_ratio,
            AVG(frame_drop_rate) AS avg_frame_drop_rate,
            AVG(detection_latency_ms) AS avg_detection_latency_ms
        FROM camera_health_logs
        GROUP BY bucket, org_id, camera_id;
        """)

        # Grant privileges on views to application role
        cursor.execute("GRANT SELECT ON TABLE events_hourly TO visionquery_app;")
        cursor.execute("GRANT SELECT ON TABLE search_queries_hourly TO visionquery_app;")
        cursor.execute("GRANT SELECT ON TABLE detections_daily TO visionquery_app;")
        cursor.execute("GRANT SELECT ON TABLE camera_health_hourly TO visionquery_app;")

    finally:
        cursor.close()
        raw_conn.autocommit = old_autocommit


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    raw_conn = bind.connection.dbapi_connection
    raw_conn.commit()
    old_autocommit = raw_conn.autocommit
    raw_conn.autocommit = True
    cursor = raw_conn.cursor()

    try:
        # Drop standard views
        cursor.execute("DROP VIEW IF EXISTS events_hourly;")
        cursor.execute("DROP VIEW IF EXISTS search_queries_hourly;")
        cursor.execute("DROP VIEW IF EXISTS detections_daily;")
        cursor.execute("DROP VIEW IF EXISTS camera_health_hourly;")

        # Drop camera_health_logs RLS policy & table
        cursor.execute("DROP POLICY IF EXISTS org_isolation ON camera_health_logs;")
        cursor.execute("DROP TABLE IF EXISTS camera_health_logs;")

        # Revert detected_objects composite primary key
        cursor.execute("ALTER TABLE detected_objects DROP CONSTRAINT IF EXISTS detected_objects_pkey;")
        cursor.execute("ALTER TABLE detected_objects ADD PRIMARY KEY (id);")

        # Revert search_queries composite primary key
        cursor.execute("ALTER TABLE search_queries DROP CONSTRAINT IF EXISTS search_queries_pkey;")
        cursor.execute("ALTER TABLE search_queries ADD PRIMARY KEY (id);")
    finally:
        cursor.close()
        raw_conn.autocommit = old_autocommit
