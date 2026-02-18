"""Custom exceptions for ResearchLineage pipeline."""


class PipelineError(Exception):
    """Base exception for all pipeline errors."""

    pass


class APIError(PipelineError):
    """API request failed."""

    pass


class RateLimitError(APIError):
    """API rate limit exceeded."""

    pass


class ValidationError(PipelineError):
    """Data validation failed."""

    pass


class DatabaseError(PipelineError):
    """Database operation failed."""

    pass


class DataQualityError(PipelineError):
    """Data quality check failed."""

    pass


class GraphConstructionError(PipelineError):
    """Graph construction failed."""

    pass
