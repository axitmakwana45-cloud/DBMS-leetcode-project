import os
from threading import RLock
from time import monotonic
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Copy .env.example to .env and configure PostgreSQL.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
metadata = MetaData()
_metadata_lock = RLock()
_metadata_refreshed_at = 0.0
_metadata_cache_seconds = 30

def refresh_metadata():
    global metadata, _metadata_refreshed_at
    with _metadata_lock:
        if not metadata.tables or monotonic() - _metadata_refreshed_at >= _metadata_cache_seconds:
            refreshed = MetaData()
            refreshed.reflect(bind=engine)
            metadata = refreshed
            _metadata_refreshed_at = monotonic()
    return metadata
