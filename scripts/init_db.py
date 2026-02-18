"""Initialize database schema for ResearchLineage."""
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Database connection string
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
    f"/{os.getenv('POSTGRES_DB')}"
)

# SQL schema from your database design
SCHEMA_SQL = """
-- Papers table
CREATE TABLE IF NOT EXISTS papers (
    paperId TEXT PRIMARY KEY,
    arxivId TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    citationCount INTEGER DEFAULT 0,
    influentialCitationCount INTEGER DEFAULT 0,
    urls TEXT,
    first_queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query_count INTEGER DEFAULT 1,
    text_availability TEXT DEFAULT 'abstract only'
);

-- LLM Generated Info table
CREATE TABLE IF NOT EXISTS llm_generated_info (
    info_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paperId),
    breakthrough_level TEXT,
    problem_addressed TEXT,
    core_method TEXT,
    key_innovation TEXT,
    limitation TEXT,
    explanation_eli5 TEXT,
    explanation_intuitive TEXT,
    explanation_technical TEXT,
    is_target_paper BOOLEAN DEFAULT FALSE,
    is_stale BOOLEAN DEFAULT FALSE
);

-- Authors table
CREATE TABLE IF NOT EXISTS authors (
    paper_id TEXT REFERENCES papers(paperId),
    author_id TEXT,
    author_name TEXT,
    PRIMARY KEY (paper_id, author_id)
);

-- LineagePapers table
CREATE TABLE IF NOT EXISTS lineage_papers (
    lineage_paper_id TEXT PRIMARY KEY,
    target_paperid TEXT REFERENCES papers(paperId),
    paperId TEXT REFERENCES papers(paperId),
    position_in_chain INTEGER NOT NULL
);

-- PaperConnections table
CREATE TABLE IF NOT EXISTS paper_connections (
    connection_id TEXT PRIMARY KEY,
    target_paperid TEXT REFERENCES papers(paperId),
    from_lineage_paper_id TEXT REFERENCES lineage_papers(lineage_paper_id),
    to_lineage_paper_id TEXT REFERENCES lineage_papers(lineage_paper_id),
    how_it_improved TEXT
);

-- Citations table
CREATE TABLE IF NOT EXISTS citations (
    fromPaperId TEXT REFERENCES papers(paperId),
    toPaperId TEXT REFERENCES papers(paperId),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fromPaperId, toPaperId)
);

-- PaperReachability table (Transitive Closure Cache)
CREATE TABLE IF NOT EXISTS paper_reachability (
    seedPaperId TEXT REFERENCES papers(paperId),
    ancestorPaperId TEXT REFERENCES papers(paperId),
    descendantPaperId TEXT REFERENCES papers(paperId),
    seedDepth INTEGER NOT NULL,
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (seedPaperId, ancestorPaperId, descendantPaperId)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_citation_count ON papers(citationCount);
CREATE INDEX IF NOT EXISTS idx_citations_from ON citations(fromPaperId);
CREATE INDEX IF NOT EXISTS idx_citations_to ON citations(toPaperId);
CREATE INDEX IF NOT EXISTS idx_lineage_target ON lineage_papers(target_paperid);
CREATE INDEX IF NOT EXISTS idx_reachability_seed ON paper_reachability(seedPaperId);
"""


def init_database():
    """Initialize database schema."""
    print(f"Connecting to database: {DATABASE_URL}")

    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            print("Executing schema creation...")
            conn.execute(text(SCHEMA_SQL))
            print("Database schema created successfully")

    except Exception as e:
        print(f"Error creating schema: {e}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    init_database()
