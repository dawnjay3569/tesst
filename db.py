# db.py
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment from .env or .env.local
load_dotenv(".env.local", override=True)
load_dotenv()

# --- SQLAlchemy imports ---
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
import sqlalchemy

# --- Database configuration from environment or DATABASE_URL ---
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    # Expect Oracle connection pieces via env vars
    DB_DRIVER = os.getenv("DB_DRIVER", "oracle+oracledb")
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_SERVICE = os.getenv("DB_SERVICE")

    if DB_USER and DB_PASS and DB_HOST and DB_PORT and DB_SERVICE:
        user_enc = quote_plus(DB_USER)
        pass_enc = quote_plus(DB_PASS)
        # Construct SQLAlchemy >=2 style URL for python-oracledb
        url_driver = DB_DRIVER or "oracle+oracledb"
        DATABASE_URL = f"{url_driver}://{user_enc}:{pass_enc}@{DB_HOST}:{DB_PORT}/?service_name={DB_SERVICE}"
    else:
        raise RuntimeError(
            "No DATABASE_URL set and missing some DB_* environment variables for Oracle connection.\n"
            "Set DATABASE_URL or provide DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_SERVICE to configure Oracle."
        )

# --- Engine creation ---
def _make_engine(url: str) -> Engine:
    # For modern SQLAlchemy (>=2.0) and python-oracledb, create_engine with the URL is sufficient.
    return create_engine(url, future=True)


engine = _make_engine(DATABASE_URL)

# --- Public API ---
def get_engine() -> Engine:
    return engine

def test_connection(timeout_seconds: int = 5) -> dict:
    try:
        with engine.connect() as conn:
            return {"ok": True, "dialect": engine.dialect.name, "message": "connected"}
    except Exception as exc:
        return {"ok": False, "dialect": getattr(engine, "dialect", None), "message": str(exc)}
