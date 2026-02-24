"""Database connection management."""
import os
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Singleton database connection pool for local/Airflow Postgres.
    
    Uses environment variables:
        - POSTGRES_USER
        - POSTGRES_PASSWORD
        - POSTGRES_HOST
        - POSTGRES_PORT
        - POSTGRES_DB
    """

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
        # Check if running in Docker (Airflow sets AIRFLOW_HOME)
        is_docker = os.getenv("AIRFLOW_HOME") is not None

        db_host = (
            os.getenv("POSTGRES_HOST_DOCKER", "postgres")
            if is_docker
            else os.getenv("POSTGRES_HOST", "localhost")
        )

        database_url = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{db_host}:{os.getenv('POSTGRES_PORT')}"
            f"/{os.getenv('POSTGRES_DB')}"
        )

        logger.debug(
            "Initializing DatabaseConnection: host=%s port=%s db=%s",
            os.getenv('POSTGRES_HOST'),
            os.getenv('POSTGRES_PORT'),
            os.getenv('POSTGRES_DB'),
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


class CloudSQLConnection:
    """
    Singleton database connection pool for Cloud SQL (GCP) via proxy.
    
    Uses environment variables:
        - CLOUD_SQL_USER
        - CLOUD_SQL_PASSWORD
        - CLOUD_SQL_HOST
        - CLOUD_SQL_PORT
        - CLOUD_SQL_DB
    """

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
            f"postgresql://{os.getenv('CLOUD_SQL_USER')}:{os.getenv('CLOUD_SQL_PASSWORD')}"
            f"@{os.getenv('CLOUD_SQL_HOST')}:{os.getenv('CLOUD_SQL_PORT')}"
            f"/{os.getenv('CLOUD_SQL_DB')}"
        )

        logger.debug(
            "Initializing CloudSQLConnection: host=%s port=%s db=%s",
            os.getenv('CLOUD_SQL_HOST'),
            os.getenv('CLOUD_SQL_PORT'),
            os.getenv('CLOUD_SQL_DB'),
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
