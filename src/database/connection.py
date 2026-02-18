"""Database connection management."""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")


class DatabaseConnection:
    """Singleton database connection pool."""

    _instance = None
    _engine = None
    _SessionLocal = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialize_engine()
        return cls._instance

    @classmethod
    def _initialize_engine(cls):
        """Initialize database engine and session factory."""
        database_url = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
            f"/{os.getenv('POSTGRES_DB')}"
        )

        cls._engine = create_engine(
            database_url, pool_size=20, max_overflow=10, pool_pre_ping=True
        )

        cls._SessionLocal = sessionmaker(
            bind=cls._engine, autocommit=False, autoflush=False
        )

    @contextmanager
    def get_session(self):
        """Get database session with automatic commit/rollback."""
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
