"""Query local Docker PostgreSQL database."""
from sqlalchemy import create_engine, text

# Local Docker database connection
LOCAL_DB_URL = "postgresql://postgres:postgres@localhost:5432/research_lineage"


def query_local_db():
    """Query local database."""
    engine = create_engine(LOCAL_DB_URL)

    print("\n" + "=" * 60)
    print("LOCAL DATABASE QUERY")
    print("=" * 60)

    try:
        with engine.connect() as conn:
            # Count papers
            result = conn.execute(text("SELECT COUNT(*) FROM papers"))
            paper_count = result.scalar()
            print(f"\nTotal Papers: {paper_count}")

            # Count authors
            result = conn.execute(text("SELECT COUNT(*) FROM authors"))
            author_count = result.scalar()
            print(f"Total Authors: {author_count}")

            # Count citations
            result = conn.execute(text("SELECT COUNT(*) FROM citations"))
            citation_count = result.scalar()
            print(f"Total Citations: {citation_count}")

            # Show top papers by citation count
            print("\nTop 10 Papers by Citation Count:")
            result = conn.execute(
                text(
                    """
                SELECT paperId, title, year, citationCount
                FROM papers
                ORDER BY citationCount DESC
                LIMIT 10
            """
                )
            )

            for i, row in enumerate(result, 1):
                print(f"  {i}. {row.title[:60]}")
                print(f"     Year: {row.year}, Citations: {row.citationcount:,}")

            # Show citations by direction
            print("\nCitations by Direction:")
            result = conn.execute(
                text(
                    """
                SELECT direction, COUNT(*) as count
                FROM citations
                GROUP BY direction
            """
                )
            )

            for row in result:
                print(f"  {row.direction}: {row.count}")

            print("\n" + "=" * 60)

    except Exception as e:
        print(f"\nError querying database: {e}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    query_local_db()
