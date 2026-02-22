"""Debug database cache."""
from src.database.connection import DatabaseConnection
from src.database.repositories import PaperRepository

db = DatabaseConnection()

with db.get_session() as session:
    repo = PaperRepository(session)
    paper = repo.get_by_id("204e3073870fae3d05bcbc2f6a8e263d9b72e776")

    if paper:
        print("Paper found in DB:")
        for key, value in paper.items():
            print(f"  {key}: {type(value).__name__}")
    else:
        print("Paper not found in DB")
