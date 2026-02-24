"""Schema validation task - Check if database tables exist."""
from sqlalchemy import inspect
from src.database.connection import DatabaseConnection
from src.utils.logging import get_logger
from src.utils.errors import DatabaseError

logger = get_logger(__name__)


class SchemaValidationTask:
    """Validate database schema exists before pipeline runs."""

    def execute(self) -> dict:
        """
        Check if all required tables exist in database.

        Returns:
            Schema validation report

        Raises:
            DatabaseError: If required tables are missing
        """
        logger.info("Starting schema validation")

        required_tables = [
            "papers",
            "authors",
            "citations",
            "llm_generated_info",
            "lineage_papers",
            "paper_connections",
            "paper_reachability",
            "timeline_ordering",
            "paper_relationships",
        ]

        db = DatabaseConnection()

        try:
            with db.get_session() as session:
                inspector = inspect(session.bind)
                existing_tables = inspector.get_table_names()

                # Check which tables exist
                missing_tables = []
                existing_required = []

                for table in required_tables:
                    if table in existing_tables:
                        existing_required.append(table)
                    else:
                        missing_tables.append(table)

                # Print schema for existing tables
                schema_info = {}
                for table in existing_required:
                    columns = inspector.get_columns(table)
                    schema_info[table] = [
                        {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col["nullable"],
                        }
                        for col in columns
                    ]

                # Log results
                logger.info(
                    f"Found {len(existing_required)}/{len(required_tables)} required tables"
                )

                if missing_tables:
                    error_msg = f"Missing required tables: {missing_tables}"
                    logger.error(error_msg)
                    raise DatabaseError(error_msg)

                # Print schema
                for table, columns in schema_info.items():
                    logger.info(f"\nTable: {table}")
                    for col in columns:
                        logger.info(
                            f"  - {col['name']}: {col['type']} "
                            f"{'NULL' if col['nullable'] else 'NOT NULL'}"
                        )

                logger.info("Schema validation passed - all required tables exist")

                return {
                    "tables_checked": len(required_tables),
                    "tables_found": len(existing_required),
                    "missing_tables": missing_tables,
                    "schema_info": schema_info,
                }

        except DatabaseError:
            raise
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            raise DatabaseError(f"Failed to validate schema: {e}")
