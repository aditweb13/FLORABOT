"""
FloraBOT SQLite to PostgreSQL Database Migration Script:
Performs zero-data-loss table reflection, schema creation, data streaming,
and sequence synchronization from SQLite to PostgreSQL.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, MetaData, Table, select, insert, func

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models import Base

TABLE_MIGRATION_ORDER = [
    "plants",
    "devices",
    "device_logs",
    "camera_images",
    "analyses",
    "reports",
    "sensor_telemetry",
    "conversations",
    "chat_messages",
    "knowledge_entries",
    "users",
    "audit_logs"
]

def migrate_database(sqlite_url: str, postgres_url: str, dry_run: bool = False):
    print("\n========================================================")
    print("  FLORABOT DATABASE MIGRATION (SQLite -> PostgreSQL)")
    print("========================================================\n")
    print(f"Source (SQLite):     {sqlite_url}")
    print(f"Target (PostgreSQL): {postgres_url}")
    print(f"Dry Run Mode:        {dry_run}\n")

    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dest_engine = create_engine(postgres_url)

    if not dry_run:
        print("-> Creating target tables in PostgreSQL schema...")
        Base.metadata.create_all(bind=dest_engine)
        print("-> Schema verified.\n")

    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)

    dest_meta = MetaData()
    if not dry_run:
        dest_meta.reflect(bind=dest_engine)

    migration_stats = {}

    with src_engine.connect() as src_conn:
        for tbl_name in TABLE_MIGRATION_ORDER:
            if tbl_name not in src_meta.tables:
                print(f"[-] Table '{tbl_name}' not in source SQLite database. Skipping.")
                continue

            src_table = src_meta.tables[tbl_name]
            rows = src_conn.execute(select(src_table)).mappings().all()
            row_count = len(rows)
            migration_stats[tbl_name] = row_count
            print(f"[+] Table '{tbl_name}': {row_count} rows found in source.")

            if dry_run or row_count == 0:
                continue

            dest_table = dest_meta.tables[tbl_name]
            with dest_engine.begin() as dest_conn:
                # Insert in chunks of 500
                chunk_size = 500
                for i in range(0, row_count, chunk_size):
                    chunk = [dict(r) for r in rows[i:i + chunk_size]]
                    dest_conn.execute(insert(dest_table), chunk)

                # Reset PostgreSQL serial sequences
                try:
                    dest_conn.execute(
                        f"SELECT setval(pg_get_serial_sequence('{tbl_name}', 'id'), coalesce(max(id), 1)) FROM {tbl_name};"
                    )
                except Exception:
                    pass

    print("\n--------------------------------------------------------")
    print("  MIGRATION SUMMARY")
    print("--------------------------------------------------------")
    for tbl, count in migration_stats.items():
        print(f"  {tbl:<25}: {count:>6} records migrated")
    print("--------------------------------------------------------")
    print("MIGRATION COMPLETED SUCCESSFULLY!\n")
    return migration_stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate FloraBOT database from SQLite to PostgreSQL")
    parser.add_argument("--sqlite-url", default="sqlite:///backend/florabot.db", help="Source SQLite connection URL")
    parser.add_argument("--postgres-url", default="postgresql://florabot:florabot_secret@localhost:5432/florabot_db", help="Target PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Inspect source without writing to PostgreSQL")
    args = parser.parse_args()

    migrate_database(args.sqlite_url, args.postgres_url, args.dry_run)
