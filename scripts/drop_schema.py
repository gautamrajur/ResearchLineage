"""Drop and recreate database schema."""
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
    f"/{os.getenv('POSTGRES_DB')}"
)


def drop_and_recreate():
    """Drop public schema and recreate it."""
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            print("Dropping public schema...")
            conn.execute(text("DROP SCHEMA public CASCADE"))
            print("Recreating public schema...")
            conn.execute(text("CREATE SCHEMA public"))
            print("Schema reset complete")
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    drop_and_recreate()
