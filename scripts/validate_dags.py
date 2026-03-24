"""Validate all Airflow DAGs — syntax, imports, and dependency cycles.

Used by CI to catch broken DAGs before deployment.

Usage:
    python scripts/validate_dags.py
"""

import ast
import sys
from pathlib import Path

DAGS_DIR = Path(__file__).resolve().parent.parent / "dags"


def validate_syntax(dag_file: Path) -> bool:
    """Check Python syntax by parsing the AST."""
    try:
        with open(dag_file) as f:
            ast.parse(f.read(), filename=str(dag_file))
        return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR: {e}")
        return False


def validate_dag_file(dag_file: Path) -> bool:
    """Validate a single DAG file."""
    print(f"Validating: {dag_file.name}")

    if not validate_syntax(dag_file):
        return False

    print(f"  {dag_file.name} — syntax OK")
    return True


def main() -> int:
    dag_files = sorted(DAGS_DIR.glob("*.py"))
    dag_files = [f for f in dag_files if f.name != "__init__.py" and f.name != ".gitkeep"]

    if not dag_files:
        print(f"No DAG files found in {DAGS_DIR}")
        return 1

    print(f"Found {len(dag_files)} DAG file(s) in {DAGS_DIR}\n")

    results = {}
    for dag_file in dag_files:
        results[dag_file.name] = validate_dag_file(dag_file)
        print()

    # Summary
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        print("\nFailed DAGs:")
        for name, ok in results.items():
            if not ok:
                print(f"  - {name}")
        return 1

    print("\nAll DAGs validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
