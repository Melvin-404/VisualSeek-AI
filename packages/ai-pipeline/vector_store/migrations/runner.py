import os
import sys
import importlib
import glob
import argparse
from typing import List, Optional

# Add parent directory of vector_store to sys.path to support dynamic imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from pymilvus import connections, utility

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


class MigrationTracker:
    """Tracks applied migrations in PostgreSQL, falling back to SQLite."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url
        self.use_postgres = False
        self.pg_conn = None
        self.sqlite_conn = None

        if self.db_url:
            if not HAS_PSYCOPG:
                print("Warning: DATABASE_URL is set but 'psycopg' library is not available. Falling back to SQLite.")
            else:
                # Clean protocol for psycopg
                clean_url = self.db_url
                if "postgresql+psycopg://" in clean_url:
                    clean_url = clean_url.replace("postgresql+psycopg://", "postgresql://")
                elif "postgresql+psycopg2://" in clean_url:
                    clean_url = clean_url.replace("postgresql+psycopg2://", "postgresql://")
                
                try:
                    self.pg_conn = psycopg.connect(clean_url)
                    self.use_postgres = True
                    self._init_db()
                    print("Using PostgreSQL for Milvus migration tracking.")
                    return
                except Exception as e:
                    print(f"Warning: Failed to connect to PostgreSQL: {e}. Falling back to SQLite.")
        
        # Fallback to SQLite
        db_path = os.path.join(os.getcwd(), "milvus_migrations.db")
        print(f"Using SQLite database for Milvus migration tracking at: {db_path}")
        import sqlite3
        self.sqlite_conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        """Creates the tracking table if it does not exist."""
        if self.use_postgres:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS milvus_schema_versions (
                        migration_id VARCHAR(255) PRIMARY KEY,
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                self.pg_conn.commit()
        else:
            with self.sqlite_conn:
                self.sqlite_conn.execute("""
                    CREATE TABLE IF NOT EXISTS milvus_schema_versions (
                        migration_id TEXT PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

    def get_applied_migrations(self) -> List[str]:
        """Gets sorted list of already applied migrations."""
        if self.use_postgres:
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT migration_id FROM milvus_schema_versions ORDER BY applied_at ASC")
                return [row[0] for row in cur.fetchall()]
        else:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT migration_id FROM milvus_schema_versions ORDER BY applied_at ASC")
            return [row[0] for row in cursor.fetchall()]

    def record_migration(self, migration_id: str):
        """Records a successful migration."""
        if self.use_postgres:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO milvus_schema_versions (migration_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (migration_id,)
                )
                self.pg_conn.commit()
        else:
            with self.sqlite_conn:
                self.sqlite_conn.execute(
                    "INSERT OR IGNORE INTO milvus_schema_versions (migration_id) VALUES (?)",
                    (migration_id,)
                )

    def remove_migration(self, migration_id: str):
        """Removes a migration record (on rollback)."""
        if self.use_postgres:
            with self.pg_conn.cursor() as cur:
                cur.execute("DELETE FROM milvus_schema_versions WHERE migration_id = %s", (migration_id,))
                self.pg_conn.commit()
        else:
            with self.sqlite_conn:
                self.sqlite_conn.execute("DELETE FROM milvus_schema_versions WHERE migration_id = ?", (migration_id,))

    def close(self):
        """Closes any open database connections."""
        if self.pg_conn:
            try:
                self.pg_conn.close()
            except Exception:
                pass
        if self.sqlite_conn:
            try:
                self.sqlite_conn.close()
            except Exception:
                pass


def discover_migrations() -> List[tuple[str, str]]:
    """Returns a list of sorted tuples (migration_id, file_path) from the migrations directory."""
    migrations_dir = os.path.dirname(os.path.abspath(__file__))
    pattern = os.path.join(migrations_dir, "[0-9][0-9][0-9][0-9]_*.py")
    files = glob.glob(pattern)
    migrations = []
    for f in files:
        basename = os.path.basename(f)
        migration_id = os.path.splitext(basename)[0]
        migrations.append((migration_id, f))
    migrations.sort(key=lambda x: x[0])
    return migrations


def run_migration_action(migration_id: str, action: str, env: str, ttl_seconds: int = 2592000):
    """Dynamically imports a migration module and runs the up or down action."""
    module_name = f"vector_store.migrations.{migration_id}"
    module = importlib.import_module(module_name)
    if action == "up":
        if hasattr(module, "up"):
            module.up(env=env, ttl_seconds=ttl_seconds)
        else:
            raise AttributeError(f"Migration {migration_id} does not have 'up' function.")
    elif action == "down":
        if hasattr(module, "down"):
            module.down(env=env)
        else:
            raise AttributeError(f"Migration {migration_id} does not have 'down' function.")


def main():
    parser = argparse.ArgumentParser(description="Milvus Vector Schema Migration Runner")
    parser.add_argument("--env", type=str, default="dev", help="Environment name prefix (e.g. dev, staging, prod)")
    parser.add_argument("--action", type=str, choices=["up", "down", "status"], default="up", help="Action to perform")
    parser.add_argument("--ttl", type=int, default=2592000, help="TTL seconds (default: 30 days, 0 or negative means no TTL)")
    parser.add_argument("--host", type=str, default=os.getenv("MILVUS_HOST", "localhost"), help="Milvus host")
    parser.add_argument("--port", type=str, default=os.getenv("MILVUS_PORT", "19530"), help="Milvus port")
    parser.add_argument("--db-url", type=str, default=os.getenv("DATABASE_URL"), help="PostgreSQL connection URL")
    args = parser.parse_args()

    # Connect to Milvus
    print(f"Connecting to Milvus at {args.host}:{args.port}...")
    try:
        connections.connect(alias="default", host=args.host, port=args.port)
        print("Connected to Milvus successfully.")
    except Exception as e:
        print(f"Error connecting to Milvus: {e}")
        sys.exit(1)

    # Initialize tracker
    tracker = MigrationTracker(db_url=args.db_url)
    
    # Discover migrations
    all_migrations = discover_migrations()
    applied = tracker.get_applied_migrations()

    print(f"Discovered {len(all_migrations)} migrations. {len(applied)} already applied.")

    if args.action == "status":
        print("\nMigration Status:")
        for m_id, _ in all_migrations:
            status = "APPLIED" if m_id in applied else "PENDING"
            print(f" - {m_id}: {status}")
        tracker.close()
        connections.disconnect("default")
        return

    if args.action == "up":
        pending = [m for m in all_migrations if m[0] not in applied]
        if not pending:
            print("No pending migrations to apply.")
        else:
            for m_id, _ in pending:
                print(f"Applying migration: {m_id}...")
                try:
                    run_migration_action(m_id, "up", args.env, args.ttl)
                    tracker.record_migration(m_id)
                    print(f"Successfully applied {m_id}.")
                except Exception as e:
                    print(f"Failed to apply migration {m_id}: {e}")
                    tracker.close()
                    connections.disconnect("default")
                    sys.exit(1)
    elif args.action == "down":
        if not applied:
            print("No applied migrations to roll back.")
        else:
            m_id = applied[-1]
            print(f"Rolling back last applied migration: {m_id}...")
            try:
                run_migration_action(m_id, "down", args.env)
                tracker.remove_migration(m_id)
                print(f"Successfully rolled back {m_id}.")
            except Exception as e:
                print(f"Failed to roll back migration {m_id}: {e}")
                tracker.close()
                connections.disconnect("default")
                sys.exit(1)

    tracker.close()
    connections.disconnect("default")
    print("Migration action complete.")


if __name__ == "__main__":
    main()
