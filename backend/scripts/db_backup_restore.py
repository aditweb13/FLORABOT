"""
FloraBOT Automated Database Backup, Integrity Verification & Recovery Script:
Performs non-blocking online SQLite snapshots, gzip compression, SHA-256 checksum
generation, automated recovery drills, and integrity checks.
"""

import sys
import os
import sqlite3
import gzip
import hashlib
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timezone

def calculate_sha256(file_path: Path) -> str:
    """Compute hex SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_backup(source_db_path: Path, backup_dir: Path) -> Path:
    """Create a live online backup of SQLite database with Gzip compression and SHA256."""
    source_db_path = Path(source_db_path).resolve()
    backup_dir = Path(backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not source_db_path.exists():
        raise FileNotFoundError(f"Source database not found at {source_db_path}")

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_snapshot = backup_dir / f"snapshot_{timestamp_str}.tmp.db"
    final_archive = backup_dir / f"florabot_backup_{timestamp_str}.db.gz"
    checksum_file = backup_dir / f"florabot_backup_{timestamp_str}.db.gz.sha256"

    print(f"[*] Initiating live online SQLite backup of {source_db_path.name}...")
    src_conn = sqlite3.connect(str(source_db_path))
    dest_conn = sqlite3.connect(str(temp_snapshot))
    try:
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()
        src_conn.close()

    print(f"[*] Compressing backup snapshot into {final_archive.name}...")
    with open(temp_snapshot, "rb") as f_in, gzip.open(final_archive, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

    if temp_snapshot.exists():
        temp_snapshot.unlink()

    sha256_hash = calculate_sha256(final_archive)
    checksum_file.write_text(f"{sha256_hash}  {final_archive.name}\n", encoding="utf-8")

    archive_size_kb = final_archive.stat().st_size / 1024
    print(f"[+] Backup successfully completed: {final_archive.name} ({archive_size_kb:.1f} KB)")
    print(f"[+] SHA256 Checksum: {sha256_hash}")
    return final_archive

def restore_backup(backup_gz_path: Path, target_db_path: Path) -> bool:
    """Restore database from gzip backup and verify integrity."""
    backup_gz_path = Path(backup_gz_path).resolve()
    target_db_path = Path(target_db_path).resolve()

    if not backup_gz_path.exists():
        raise FileNotFoundError(f"Backup archive not found at {backup_gz_path}")

    # Verify checksum if .sha256 file exists
    checksum_file = backup_gz_path.with_name(f"{backup_gz_path.name}.sha256")
    if checksum_file.exists():
        expected_hash = checksum_file.read_text(encoding="utf-8").strip().split()[0]
        actual_hash = calculate_sha256(backup_gz_path)
        if actual_hash.lower() != expected_hash.lower():
            raise ValueError(f"Checksum mismatch! Expected {expected_hash}, got {actual_hash}")
        print("[+] Checksum verified successfully against SHA256 manifest.")

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_restore = target_db_path.with_suffix(".restoring.tmp")

    print(f"[*] Decompressing {backup_gz_path.name} to {temp_restore.name}...")
    with gzip.open(backup_gz_path, "rb") as f_in, open(temp_restore, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    # Perform SQLite PRAGMA integrity check
    print("[*] Performing database integrity drill...")
    conn = sqlite3.connect(str(temp_restore))
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    result = cursor.fetchone()
    conn.close()

    if result and result[0] == "ok":
        print("[+] Integrity check: PASSED ('ok').")
        if target_db_path.exists():
            target_db_path.unlink()
        temp_restore.rename(target_db_path)
        print(f"[+] Database successfully restored to {target_db_path.name}")
        return True
    else:
        if temp_restore.exists():
            temp_restore.unlink()
        raise RuntimeError(f"Database integrity verification failed: {result}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FloraBOT Database Backup & Disaster Recovery")
    parser.add_argument("--action", choices=["backup", "restore"], default="backup")
    parser.add_argument("--source-db", default="backend/florabot.db", help="Source SQLite DB path")
    parser.add_argument("--backup-dir", default="backend/data/backups", help="Target backup directory")
    parser.add_argument("--archive", help="Backup archive file path for restore")
    parser.add_argument("--target-db", default="backend/florabot_restored.db", help="Target path for restore")

    args = parser.parse_args()

    if args.action == "backup":
        create_backup(Path(args.source_db), Path(args.backup_dir))
    elif args.action == "restore":
        if not args.archive:
            print("Error: --archive argument is required for restore.")
            sys.exit(1)
        restore_backup(Path(args.archive), Path(args.target_db))
