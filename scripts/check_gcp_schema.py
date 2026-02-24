"""Check existing GCP database schema."""
from sqlalchemy import create_engine, inspect

GCP_DB_URL = "postgresql://shivram:shivram@127.0.0.1:5432/researchlineage"


def check_schema():
    engine = create_engine(GCP_DB_URL)

    print("\n" + "=" * 60)
    print("GCP DATABASE SCHEMA")
    print("=" * 60)

    try:
        inspector = inspect(engine)

        # Get all tables
        tables = inspector.get_table_names()
        print(f"\nExisting Tables ({len(tables)}):")
        for table in tables:
            print(f"  - {table}")

        # For each table, show columns
        for table in tables:
            print(f"\n{table.upper()} columns:")
            columns = inspector.get_columns(table)
            for col in columns:
                print(f"  {col['name']}: {col['type']}")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    check_schema()
