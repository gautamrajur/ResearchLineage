"""
Verify DB connection and fetch_pdf_failures table using .env POSTGRES_*.
Run from project root: python scripts/check_fetch_pdf_failures_db.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from sqlalchemy import create_engine, text


def main():
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")

    if not all([user, password, host, port, db]):
        print("Missing POSTGRES_* in .env (USER, PASSWORD, HOST, PORT, DB)")
        return 1

    url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    print(f"Connecting to {host}:{port} ...")
    engine = create_engine(url, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            r = conn.execute(text("SELECT current_database()"))
            current_db = r.scalar()
            print(f"Connected to database: {current_db}")

            conn.execute(text("SELECT 1"))
            count = conn.execute(text("SELECT COUNT(*) FROM fetch_pdf_failures")).scalar()
            print(f"fetch_pdf_failures row count: {count}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
