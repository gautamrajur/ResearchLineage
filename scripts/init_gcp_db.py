"""Initialize GCP database schema."""
from pathlib import Path
from sqlalchemy import create_engine, text

# GCP connection via proxy
GCP_DB_URL = "postgresql://shivram:shivram@127.0.0.1:5432/researchlineage"

# Import schema from init_db
import sys  # noqa: E402

sys.path.append(str(Path(__file__).parent))
from init_db import SCHEMA_SQL  # noqa: E402


def init_gcp():
    print("Connecting to GCP database...")

    engine = create_engine(GCP_DB_URL)

    try:
        with engine.begin() as conn:
            # Just create tables (IF NOT EXISTS handles existing tables)
            print("Creating schema...")
            conn.execute(text(SCHEMA_SQL))

            print("GCP database schema created successfully!")
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    init_gcp()
