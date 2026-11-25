import sqlite3
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
db_paths = [backend_dir / "florabot.db", backend_dir / "data" / "florabot.db"]

for path in db_paths:
    if not path.exists():
        continue
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "knowledge_entries" not in tables:
        conn.close()
        continue
    cols = [r[1] for r in cur.execute("PRAGMA table_info(knowledge_entries)").fetchall()]
    new_cols = [
        ("citations", "TEXT DEFAULT ''"),
        ("review_date", "TEXT DEFAULT ''"),
        ("reviewed_by", "TEXT DEFAULT ''"),
        ("embedding_json", "TEXT DEFAULT '[]'")
    ]
    for col_name, col_def in new_cols:
        if col_name not in cols:
            cur.execute(f"ALTER TABLE knowledge_entries ADD COLUMN {col_name} {col_def}")
            print(f"Added {col_name} to {path.name}")
    conn.commit()
    conn.close()

# Also seed/update knowledge entries with embeddings
from app.database import engine
from sqlalchemy.orm import Session
from app.knowledge_service import seed_knowledge_base
with Session(bind=engine) as db:
    seed_knowledge_base(db)
print("Updated knowledge base seed entries with embeddings and citations.")
