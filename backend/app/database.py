from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

url = settings.database_url
if url.startswith("sqlite"):
    db_file = make_url(url).database
    if db_file and db_file != ":memory:":
        db_path = Path(db_file)
        if not db_path.is_absolute():
            # If relative, resolve relative to backend directory
            base_dir = Path(__file__).resolve().parent.parent
            db_path = base_dir / db_file
            url = f"sqlite:///{db_path.as_posix()}"
        db_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
engine_kwargs = {"connect_args": connect_args}
if url.startswith(("postgresql", "postgres")):
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 300
    })

engine = create_engine(url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
