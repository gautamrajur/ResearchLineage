"""Pydantic models for Semantic Scholar API responses."""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class Author(BaseModel):
    """Author information."""

    authorId: Optional[str] = None
    name: str


class ExternalIds(BaseModel):
    """External paper identifiers."""

    ArXiv: Optional[str] = None
    DOI: Optional[str] = None
    CorpusId: Optional[int] = None
    PubMed: Optional[str] = None


class PaperResponse(BaseModel):
    """Semantic Scholar paper metadata response."""

    paperId: str
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    citationCount: int = 0
    influentialCitationCount: int = 0
    referenceCount: int = 0
    authors: List[Author] = Field(default_factory=list)
    externalIds: Optional[ExternalIds] = None
    venue: Optional[str] = None
    publicationDate: Optional[str] = None
    url: Optional[str] = None

    @field_validator("year")
    @classmethod
    def validate_year(cls, v):
        """Validate publication year is reasonable."""
        if v and (v < 1900 or v > 2030):
            raise ValueError(f"Invalid year: {v}")
        return v


class CitationContext(BaseModel):
    """Citation with context and intent."""

    contexts: List[str] = Field(default_factory=list)
    intents: List[str] = Field(default_factory=list)
    isInfluential: bool = False
    citedPaper: PaperResponse


class ReferenceResponse(BaseModel):
    """Paper reference response."""

    contexts: List[str] = Field(default_factory=list)
    intents: List[str] = Field(default_factory=list)
    isInfluential: bool = False
    citedPaper: PaperResponse
