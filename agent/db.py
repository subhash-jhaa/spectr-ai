import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

DATABASE_URL_READONLY = os.getenv("DATABASE_URL_READONLY")

if not DATABASE_URL_READONLY:
    print("[DB] ERROR: DATABASE_URL_READONLY is missing from .env")
    sys.exit(1)

if DATABASE_URL_READONLY.startswith("postgres://"):
    DATABASE_URL_READONLY = DATABASE_URL_READONLY.replace("postgres://", "postgresql://", 1)

engine: Engine = create_engine(
    DATABASE_URL_READONLY,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

def get_engine() -> Engine:
    return engine