"""initial_schema

Revision ID: f439988e7b3a
Revises: 
Create Date: 2026-06-10 20:55:27.539454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector
import app.models.base  # For EncryptedString

# revision identifiers, used by Alembic.
revision: str = 'f439988e7b3a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create Extensions
    # op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    # 2. Create core tables
    op.create_table('organizations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('permissions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index('ix_permissions_name', 'permissions', ['name'], unique=True)
    
    op.create_table('cameras',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=False),
    sa.Column('rtsp_url', app.models.base.EncryptedString(), nullable=False),
    sa.Column('status', sa.String(length=50), server_default='offline', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cameras_org_id', 'cameras', ['org_id'], unique=False)
    
    op.create_table('roles',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', 'name', name='uq_roles_org_id_name')
    )
    op.create_index('ix_roles_org_id', 'roles', ['org_id'], unique=False)
    
    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_org_id', 'users', ['org_id'], unique=False)
    
    op.create_table('audit_log',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=True),
    sa.Column('table_name', sa.String(length=100), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('old_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("new_data IS NULL OR jsonb_typeof(new_data) = 'object'", name='chk_audit_new_data_object'),
    sa.CheckConstraint("old_data IS NULL OR jsonb_typeof(old_data) = 'object'", name='chk_audit_old_data_object'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_created_at_brin', 'audit_log', ['created_at'], unique=False, postgresql_using='brin')
    op.create_index('ix_audit_log_org_id', 'audit_log', ['org_id'], unique=False)
    op.create_index('ix_audit_log_user_id', 'audit_log', ['user_id'], unique=False)
    
    op.create_table('events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('camera_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('severity', sa.String(length=50), server_default='info', nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('thumbnail_s3_key', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("metadata ? 'source_type' AND metadata ? 'confidence_threshold'", name='chk_event_metadata_keys'),
    sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', 'start_time')
    )
    op.create_index('ix_events_camera_id', 'events', ['camera_id'], unique=False)
    op.create_index('ix_events_metadata_gin', 'events', ['metadata'], unique=False, postgresql_using='gin')
    op.create_index('ix_events_org_id', 'events', ['org_id'], unique=False)
    op.create_index('ix_events_start_time_brin', 'events', ['start_time'], unique=False, postgresql_using='brin')
    
    # Convert events to a TimescaleDB hypertable
    # op.execute("SELECT create_hypertable('events', 'start_time');")

    op.create_table('role_permissions',
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('permission_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_index('ix_role_permissions_permission_id', 'role_permissions', ['permission_id'], unique=False)
    
    op.create_table('search_queries',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('query_embedding', sa.ARRAY(sa.Float), nullable=False),
    sa.Column('results_count', sa.Integer(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_search_queries_created_at_brin', 'search_queries', ['created_at'], unique=False, postgresql_using='brin')
    op.create_index('ix_search_queries_org_id', 'search_queries', ['org_id'], unique=False)
    op.create_index('ix_search_queries_user_id', 'search_queries', ['user_id'], unique=False)
    
    op.create_table('user_roles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'], unique=False)
    
    op.create_table('video_segments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('camera_id', sa.UUID(), nullable=False),
    sa.Column('s3_key', sa.String(length=512), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('fps', sa.Integer(), nullable=False),
    sa.Column('resolution', sa.String(length=50), nullable=False),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('processing_status', sa.String(length=50), server_default='pending', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', 'start_time'),
    postgresql_partition_by='RANGE (start_time)'
    )
    op.create_index('ix_video_segments_camera_id', 'video_segments', ['camera_id'], unique=False)
    op.create_index('ix_video_segments_org_id', 'video_segments', ['org_id'], unique=False)
    op.create_index('ix_video_segments_start_time_brin', 'video_segments', ['start_time'], unique=False, postgresql_using='brin')

    # Pre-create monthly partitions for video_segments from 2026-01 to 2030-12
    op.execute("""
    DO $$
    DECLARE
        start_date DATE := '2026-01-01';
        end_date DATE := '2031-01-01';
        curr_date DATE := start_date;
        partition_name TEXT;
        next_month DATE;
    BEGIN
        WHILE curr_date < end_date LOOP
            next_month := curr_date + INTERVAL '1 month';
            partition_name := 'video_segments_' || to_char(curr_date, 'YYYY_MM');
            EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF video_segments FOR VALUES FROM (%L) TO (%L)', partition_name, curr_date, next_month);
            curr_date := next_month;
        END LOOP;
    END $$;
    """)

    op.create_table('detected_objects',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('segment_id', sa.UUID(), nullable=False),
    sa.Column('segment_start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('frame_number', sa.Integer(), nullable=False),
    sa.Column('timestamp_ms', sa.Integer(), nullable=False),
    sa.Column('class_label', sa.String(length=100), nullable=False),
    sa.Column('confidence', sa.Double(), nullable=False),
    sa.Column('bbox_x', sa.Double(), nullable=False),
    sa.Column('bbox_y', sa.Double(), nullable=False),
    sa.Column('bbox_w', sa.Double(), nullable=False),
    sa.Column('bbox_h', sa.Double(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['segment_id', 'segment_start_time'], ['video_segments.id', 'video_segments.start_time'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_detected_objects_class_label', 'detected_objects', ['class_label'], unique=False)
    op.create_index('ix_detected_objects_created_at_brin', 'detected_objects', ['created_at'], unique=False, postgresql_using='brin')
    op.create_index('ix_detected_objects_org_id', 'detected_objects', ['org_id'], unique=False)
    op.create_index('ix_detected_objects_segment_id_start_time', 'detected_objects', ['segment_id', 'segment_start_time'], unique=False)
    op.create_index('ix_detected_objects_track_id', 'detected_objects', ['track_id'], unique=False)

    # 3. Create Audit protection trigger functions & DML logging trigger functions
    op.execute("""
    CREATE OR REPLACE FUNCTION protect_audit_log() RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Audit log is immutable and append-only.';
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER audit_log_immutable_trg
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION protect_audit_log();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION log_dml_operation() RETURNS TRIGGER AS $$
    DECLARE
        v_org_id UUID;
        v_user_id UUID;
        v_ip VARCHAR;
        v_old_data JSONB := NULL;
        v_new_data JSONB := NULL;
        v_action VARCHAR := TG_OP;
        v_table VARCHAR := TG_TABLE_NAME;
    BEGIN
        BEGIN
            v_org_id := NULLIF(current_setting('app.current_org_id', true), '')::uuid;
        EXCEPTION WHEN OTHERS THEN
            v_org_id := NULL;
        END;

        BEGIN
            v_user_id := NULLIF(current_setting('app.current_user_id', true), '')::uuid;
        EXCEPTION WHEN OTHERS THEN
            v_user_id := NULL;
        END;

        v_ip := host(inet_client_addr());

        IF TG_OP = 'DELETE' THEN
            v_old_data := to_jsonb(OLD);
            IF v_org_id IS NULL THEN
                BEGIN
                    v_org_id := (v_old_data->>'org_id')::uuid;
                EXCEPTION WHEN OTHERS THEN
                    v_org_id := NULL;
                END;
            END IF;
        ELSIF TG_OP = 'UPDATE' THEN
            v_old_data := to_jsonb(OLD);
            v_new_data := to_jsonb(NEW);
            IF v_org_id IS NULL THEN
                BEGIN
                    v_org_id := (v_new_data->>'org_id')::uuid;
                EXCEPTION WHEN OTHERS THEN
                    v_org_id := NULL;
                END;
            END IF;
        ELSIF TG_OP = 'INSERT' THEN
            v_new_data := to_jsonb(NEW);
            IF v_org_id IS NULL THEN
                BEGIN
                    v_org_id := (v_new_data->>'org_id')::uuid;
                EXCEPTION WHEN OTHERS THEN
                    v_org_id := NULL;
                END;
            END IF;
        END IF;

        INSERT INTO audit_log (
            org_id,
            table_name,
            action,
            old_data,
            new_data,
            query_text,
            user_id,
            ip_address
        ) VALUES (
            v_org_id,
            v_table,
            v_action,
            v_old_data,
            v_new_data,
            current_query(),
            v_user_id,
            v_ip
        );

        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Attach DML logger trigger to all tables except audit_log
    dml_tables = [
        'organizations', 'users', 'roles', 'permissions', 'user_roles', 'role_permissions',
        'cameras', 'video_segments', 'detected_objects', 'events', 'search_queries'
    ]
    for table in dml_tables:
        op.execute(f"""
        CREATE TRIGGER log_dml_trg_{table}
        AFTER INSERT OR UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION log_dml_operation();
        """)

    # 4. Enable Row-Level Security (RLS) on all tenant tables and configure policies
    tenant_tables = [
        'organizations', 'users', 'roles', 'user_roles', 'role_permissions',
        'cameras', 'video_segments', 'detected_objects', 'events', 'search_queries', 'audit_log'
    ]
    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        if table == 'organizations':
            op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            FOR ALL
            USING (id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
            """)
        elif table in ('user_roles', 'role_permissions'):
            op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            FOR ALL
            USING (role_id IN (SELECT id FROM roles WHERE org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid));
            """)
        else:
            op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
            """)

    # 5. Create application role and grant permissions
    op.execute("CREATE ROLE visionquery_app WITH LOGIN PASSWORD 'postgres';")
    op.execute("GRANT USAGE ON SCHEMA public TO visionquery_app;")
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO visionquery_app;")
    op.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO visionquery_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO visionquery_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO visionquery_app;")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop role
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM visionquery_app;")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM visionquery_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM visionquery_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM visionquery_app;")
    op.execute("DROP ROLE IF EXISTS visionquery_app;")

    tenant_tables = [
        'organizations', 'users', 'roles', 'user_roles', 'role_permissions',
        'cameras', 'video_segments', 'detected_objects', 'events', 'search_queries', 'audit_log'
    ]
    
    # 1. Disable RLS and drop policies
    for table in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # 2. Drop DML triggers and functions
    dml_tables = [
        'organizations', 'users', 'roles', 'permissions', 'user_roles', 'role_permissions',
        'cameras', 'video_segments', 'detected_objects', 'events', 'search_queries'
    ]
    for table in dml_tables:
        op.execute(f"DROP TRIGGER IF EXISTS log_dml_trg_{table} ON {table};")
    op.execute("DROP FUNCTION IF EXISTS log_dml_operation();")

    # 3. Drop audit immutability triggers and functions
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutable_trg ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS protect_audit_log();")

    # 4. Drop tables in correct dependency order
    op.drop_index('ix_detected_objects_track_id', table_name='detected_objects')
    op.drop_index('ix_detected_objects_segment_id_start_time', table_name='detected_objects')
    op.drop_index('ix_detected_objects_org_id', table_name='detected_objects')
    op.drop_index('ix_detected_objects_created_at_brin', table_name='detected_objects', postgresql_using='brin')
    op.drop_index('ix_detected_objects_class_label', table_name='detected_objects')
    op.drop_table('detected_objects')
    
    op.drop_index('ix_video_segments_start_time_brin', table_name='video_segments', postgresql_using='brin')
    op.drop_index('ix_video_segments_org_id', table_name='video_segments')
    op.drop_index('ix_video_segments_camera_id', table_name='video_segments')
    op.drop_table('video_segments')
    
    op.drop_index('ix_user_roles_role_id', table_name='user_roles')
    op.drop_table('user_roles')
    
    op.drop_index('ix_search_queries_user_id', table_name='search_queries')
    op.drop_index('ix_search_queries_org_id', table_name='search_queries')
    op.drop_index('ix_search_queries_created_at_brin', table_name='search_queries', postgresql_using='brin')
    op.drop_table('search_queries')
    
    op.drop_index('ix_role_permissions_permission_id', table_name='role_permissions')
    op.drop_table('role_permissions')
    
    op.drop_index('ix_events_start_time_brin', table_name='events', postgresql_using='brin')
    op.drop_index('ix_events_org_id', table_name='events')
    op.drop_index('ix_events_metadata_gin', table_name='events', postgresql_using='gin')
    op.drop_index('ix_events_camera_id', table_name='events')
    op.drop_table('events')
    
    op.drop_index('ix_audit_log_user_id', table_name='audit_log')
    op.drop_index('ix_audit_log_org_id', table_name='audit_log')
    op.drop_index('ix_audit_log_created_at_brin', table_name='audit_log', postgresql_using='brin')
    op.drop_table('audit_log')
    
    op.drop_index('ix_users_org_id', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
    
    op.drop_index('ix_roles_org_id', table_name='roles')
    op.drop_table('roles')
    
    op.drop_index('ix_cameras_org_id', table_name='cameras')
    op.drop_table('cameras')
    
    op.drop_index('ix_permissions_name', table_name='permissions')
    op.drop_table('permissions')
    
    op.drop_table('organizations')

    # 5. Drop Extensions (optional, but safe to keep, we will drop vector scale/timescale in reverse)
    # op.execute("DROP EXTENSION IF EXISTS timescaledb;")
    # op.execute("DROP EXTENSION IF EXISTS vector;")
