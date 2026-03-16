"""Flatten nested TreeView trees into flat arrays with depth and parentId."""


def _extract_paper_fields(paper: dict) -> dict:
    """Extract the standard fields from a Semantic Scholar paper dict."""
    return {
        "paperId": paper.get("paperId", ""),
        "title": paper.get("title", "Unknown"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount", 0),
    }


def flatten_ancestors(ancestors: list, seed_id: str, depth: int = 1) -> list[dict]:
    """Flatten nested ancestor tree into flat list with depth and parentId.

    Each ancestor node looks like: {paper: {...}, ancestors: [...]}
    At depth=1, parentId is the seed paper.
    At deeper depths, parentId is the paper that cited this ancestor.
    """
    result = []
    for node in ancestors:
        paper = node.get("paper", {})
        if not paper.get("paperId"):
            continue

        flat = _extract_paper_fields(paper)
        flat["depth"] = depth
        flat["parentId"] = seed_id
        result.append(flat)

        # Recurse into deeper ancestors
        children = node.get("ancestors", [])
        if children:
            result.extend(
                flatten_ancestors(children, paper["paperId"], depth + 1)
            )

    return result


def flatten_descendants(descendants: list, seed_id: str, depth: int = 1) -> list[dict]:
    """Flatten nested descendant tree into flat list with depth and parentId.

    Each descendant node looks like: {paper: {...}, children: [...]}
    At depth=1, parentId is the seed paper.
    At deeper depths, parentId is the paper that was cited.
    """
    result = []
    for node in descendants:
        paper = node.get("paper", {})
        if not paper.get("paperId"):
            continue

        flat = _extract_paper_fields(paper)
        flat["depth"] = depth
        flat["parentId"] = seed_id
        result.append(flat)

        # Recurse into children
        children = node.get("children", [])
        if children:
            result.extend(
                flatten_descendants(children, paper["paperId"], depth + 1)
            )

    return result
