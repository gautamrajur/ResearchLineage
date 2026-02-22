"""Generate Timeline View - Chronological narrative of research lineage."""
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import httpx

load_dotenv()

# Database connection
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
    f"/{os.getenv('POSTGRES_DB')}"
)

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"


def query_backward_lineage(target_paper_id: str, engine):
    """
    Query papers in backward lineage (papers the target cites).

    Returns papers sorted chronologically.
    """
    query = text(
        """
        WITH RECURSIVE lineage AS (
            -- Start with target paper
            SELECT p.paperId, p.title, p.abstract, p.year,
                   p.citationCount, p.venue, 0 as depth
            FROM papers p
            WHERE p.paperId = :target_id

            UNION

            -- Recursively get papers it cites (backward)
            SELECT p.paperId, p.title, p.abstract, p.year,
                   p.citationCount, p.venue, l.depth + 1
            FROM papers p
            JOIN citations c ON c.toPaperId = p.paperId
            JOIN lineage l ON l.paperId = c.fromPaperId
            WHERE c.direction = 'backward' AND l.depth < 3
        )
        SELECT DISTINCT paperId, title, abstract, year, citationCount, venue, depth
        FROM lineage
        ORDER BY year ASC, citationCount DESC
    """
    )

    with engine.connect() as conn:
        result = conn.execute(query, {"target_id": target_paper_id})
        papers = [dict(row._mapping) for row in result]

    return papers


def query_citation_contexts(from_paper_id: str, to_paper_id: str, engine):
    """Get citation contexts between two papers."""
    query = text(
        """
        SELECT contexts, intents, isInfluential
        FROM citations
        WHERE fromPaperId = :from_id AND toPaperId = :to_id
    """
    )

    with engine.connect() as conn:
        result = conn.execute(query, {"from_id": from_paper_id, "to_id": to_paper_id})
        row = result.fetchone()
        if row:
            return dict(row._mapping)
    return None


def call_llama(prompt: str, max_tokens: int = 500) -> str:
    """Call Ollama API to generate text."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": max_tokens},
    }

    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=60.0)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except Exception as e:
        print(f"Error calling Llama: {e}")
        return f"[Error generating response: {e}]"


def generate_timeline_narrative(papers: list, engine) -> str:
    """Generate chronological narrative using Llama."""

    # Build context for LLM
    papers_context = []
    for i, paper in enumerate(papers, 1):
        year = paper["year"] or "Unknown"
        abstract = (
            paper["abstract"][:300] if paper["abstract"] else "No abstract available"
        )

        papers_context.append(
            f"{i}. [{year}] {paper['title']}\n"
            f"   Citations: {paper['citationcount']}\n"
            f"   Summary: {abstract}...\n"
        )

    context_text = "\n".join(papers_context)

    prompt = f"""You are a research historian analyzing how scientific ideas evolved.

Given these papers in chronological order from a research lineage leading to the Transformer architecture:

{context_text}

Task: Create a narrative explaining how these ideas evolved chronologically. For each paper:
1. What problem did it solve?
2. What key innovation did it introduce?
3. How did it build upon previous work?

Write a clear, chronological narrative (3-4 paragraphs) explaining the research lineage from earliest to most recent paper.
Focus on the progression of ideas, not just listing papers.
"""

    print("\nGenerating narrative with Llama...")
    narrative = call_llama(prompt, max_tokens=800)

    return narrative


def generate_html_report(papers: list, narrative: str, target_paper_id: str):
    """Generate HTML report with timeline view."""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Research Lineage Timeline</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .narrative {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            line-height: 1.8;
        }}
        .timeline {{
            position: relative;
            padding-left: 40px;
        }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 10px;
            top: 0;
            bottom: 0;
            width: 3px;
            background: #667eea;
        }}
        .paper {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            position: relative;
        }}
        .paper::before {{
            content: '';
            position: absolute;
            left: -34px;
            top: 25px;
            width: 15px;
            height: 15px;
            border-radius: 50%;
            background: #667eea;
            border: 3px solid white;
        }}
        .paper.target {{
            border: 3px solid #667eea;
        }}
        .paper-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 15px;
        }}
        .paper-title {{
            font-size: 18px;
            font-weight: bold;
            color: #333;
            flex: 1;
        }}
        .paper-year {{
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
        }}
        .paper-meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .paper-abstract {{
            color: #444;
            font-size: 14px;
            line-height: 1.6;
            margin-top: 10px;
        }}
        .target-badge {{
            background: #ff6b6b;
            color: white;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Research Lineage Timeline View</h1>
        <p>Chronological narrative showing how ideas evolved</p>
        <p style="font-size: 14px; opacity: 0.9;">Target Paper: {papers[-1]['title'] if papers else 'N/A'}</p>
    </div>

    <div class="narrative">
        <h2>Research Evolution Narrative</h2>
        <p style="white-space: pre-wrap;">{narrative}</p>
        <p style="font-size: 12px; color: #666; margin-top: 20px; font-style: italic;">
            Generated by Llama 3.2 analyzing {len(papers)} papers in chronological order
        </p>
    </div>

    <h2 style="margin-top: 40px; margin-bottom: 20px;">Chronological Paper Sequence</h2>
    <div class="timeline">
"""

    # Add papers to timeline
    for paper in papers:
        is_target = paper["paperid"] == target_paper_id
        target_class = " target" if is_target else ""
        target_badge = '<span class="target-badge">TARGET</span>' if is_target else ""

        abstract = (
            paper["abstract"][:400] if paper["abstract"] else "No abstract available"
        )

        html += f"""
        <div class="paper{target_class}">
            <div class="paper-header">
                <div class="paper-title">{paper['title']}{target_badge}</div>
                <div class="paper-year">{paper['year'] or 'Unknown'}</div>
            </div>
            <div class="paper-meta">
                📊 Citations: {paper['citationcount']:,} |
                📍 Venue: {paper['venue'] or 'N/A'}
            </div>
            <div class="paper-abstract">{abstract}...</div>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    return html


def main():
    """Generate timeline view."""
    print("\n" + "=" * 60)
    print("TIMELINE VIEW GENERATOR")
    print("=" * 60)

    # Get target paper ID from user
    target_paper_id = input(
        "\nEnter target paper ID (press Enter for Transformer paper): "
    ).strip()
    if not target_paper_id:
        target_paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"

    # Connect to database
    print("\nConnecting to database...")
    engine = create_engine(DATABASE_URL)

    # Query lineage papers
    print(f"Querying backward lineage for {target_paper_id}...")
    papers = query_backward_lineage(target_paper_id, engine)

    if not papers:
        print("No papers found in database for this ID!")
        return

    print(f"Found {len(papers)} papers in lineage")

    # Generate narrative with Llama
    narrative = generate_timeline_narrative(papers, engine)

    # Generate HTML report
    print("\nGenerating HTML report...")
    html = generate_html_report(papers, narrative, target_paper_id)

    # Save to file
    output_file = Path("timeline_view.html")
    output_file.write_text(html, encoding="utf-8")

    print(f"\n✓ Timeline view generated: {output_file.absolute()}")
    print(f"\nOpen {output_file.name} in your browser to view the report!")

    engine.dispose()


if __name__ == "__main__":
    main()
