"""Initialize database schema for ResearchLineage."""
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Database connection string
"""DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
    f"/{os.getenv('POSTGRES_DB')}"
)"""

# At the top, replace the DATABASE_URL with GCP directly
DATABASE_URL = "postgresql://shivram:shivram@136.111.19.109:5432/researchlineage"

# SQL schema
SCHEMA_SQL = """
-- Papers table
CREATE TABLE IF NOT EXISTS papers (
    paperId TEXT PRIMARY KEY,
    arxivId TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    year INTEGER,
    citationCount INTEGER DEFAULT 0,
    influentialCitationCount INTEGER DEFAULT 0,
    referenceCount INTEGER DEFAULT 0,
    venue TEXT,
    urls TEXT,
    first_queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query_count INTEGER DEFAULT 1,
    text_availability TEXT DEFAULT 'abstract only'
);

-- LLM Generated Info table
CREATE TABLE IF NOT EXISTS llm_generated_info (
    info_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paperId) ON DELETE CASCADE,
    breakthrough_level TEXT,
    problem_addressed TEXT,
    core_method TEXT,
    key_innovation TEXT,
    limitation TEXT,
    explanation_eli5 TEXT,
    explanation_intuitive TEXT,
    explanation_technical TEXT,
    is_target_paper BOOLEAN DEFAULT FALSE,
    is_stale BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Authors table
CREATE TABLE IF NOT EXISTS authors (
    paper_id TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    author_id TEXT,
    author_name TEXT,
    PRIMARY KEY (paper_id, author_id)
);

-- LineagePapers table
CREATE TABLE IF NOT EXISTS lineage_papers (
    lineage_paper_id TEXT PRIMARY KEY,
    target_paperid TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    paperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    position_in_chain INTEGER NOT NULL,
    direction TEXT DEFAULT 'backward'
);

-- PaperConnections table
CREATE TABLE IF NOT EXISTS paper_connections (
    connection_id TEXT PRIMARY KEY,
    target_paperid TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    from_lineage_paper_id TEXT REFERENCES lineage_papers(lineage_paper_id) ON DELETE CASCADE,
    to_lineage_paper_id TEXT REFERENCES lineage_papers(lineage_paper_id) ON DELETE CASCADE,
    how_it_improved TEXT
);

-- Citations table
CREATE TABLE IF NOT EXISTS citations (
    fromPaperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    toPaperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    isInfluential BOOLEAN DEFAULT FALSE,
    contexts TEXT[],
    intents TEXT[],
    direction TEXT DEFAULT 'backward',
    PRIMARY KEY (fromPaperId, toPaperId)
);

-- PaperReachability table (Transitive Closure Cache)
CREATE TABLE IF NOT EXISTS paper_reachability (
    seedPaperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    ancestorPaperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    descendantPaperId TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    seedDepth INTEGER NOT NULL,
    direction TEXT DEFAULT 'backward',
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (seedPaperId, ancestorPaperId, descendantPaperId)
);

-- Timeline ordering for narrative view
CREATE TABLE IF NOT EXISTS timeline_ordering (
    timeline_id TEXT PRIMARY KEY,
    target_paperid TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    ordered_paper_ids TEXT[],
    narrative_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Conceptual paper relationships (LLM-generated)
CREATE TABLE IF NOT EXISTS paper_relationships (
    relationship_id TEXT PRIMARY KEY,
    from_paper_id TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    to_paper_id TEXT REFERENCES papers(paperId) ON DELETE CASCADE,
    relationship_type TEXT,
    explanation TEXT,
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_citation_count ON papers(citationCount);
CREATE INDEX IF NOT EXISTS idx_citations_from ON citations(fromPaperId);
CREATE INDEX IF NOT EXISTS idx_citations_to ON citations(toPaperId);
CREATE INDEX IF NOT EXISTS idx_citations_direction ON citations(direction);
CREATE INDEX IF NOT EXISTS idx_lineage_target ON lineage_papers(target_paperid);
CREATE INDEX IF NOT EXISTS idx_lineage_direction ON lineage_papers(direction);
CREATE INDEX IF NOT EXISTS idx_reachability_seed ON paper_reachability(seedPaperId);
CREATE INDEX IF NOT EXISTS idx_reachability_direction ON paper_reachability(direction);
CREATE INDEX IF NOT EXISTS idx_llm_info_paper ON llm_generated_info(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_rel_from ON paper_relationships(from_paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_rel_to ON paper_relationships(to_paper_id);
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
