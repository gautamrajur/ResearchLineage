"""
Unit tests for src.utils.errors: exception hierarchy and messages (pytest).
"""
import pytest
from src.utils.errors import (
    PipelineError,
    APIError,
    RateLimitError,
    ValidationError,
    DatabaseError,
    DataQualityError,
    GraphConstructionError,
)


def test_pipeline_base():
    """PipelineError is base; others inherit from it."""
    e = PipelineError("base")
    assert str(e) == "base"
    assert isinstance(e, Exception)


def test_pipeline_msg_edge_cases():
    """PipelineError: empty message and long/special-character messages."""
    # Empty message
    e = PipelineError("")
    assert str(e) == ""

    # Long message
    long_msg = "x" * 10_000
    e_long = PipelineError(long_msg)
    assert str(e_long) == long_msg

    # Special characters: newlines, quotes, unicode
    special = "Error: line1\nline2\t tab, \"quotes\", 'apostrophe', 日本"
    e_special = PipelineError(special)
    assert str(e_special) == special


def test_api_inherits_pipeline():
    """APIError inherits from PipelineError."""
    e = APIError("api failed")
    assert isinstance(e, PipelineError)
    assert str(e) == "api failed"


def test_rate_limit_inherits_api():
    """RateLimitError inherits from APIError and PipelineError."""
    e = RateLimitError("429")
    assert isinstance(e, APIError)
    assert isinstance(e, PipelineError)
    assert str(e) == "429"


def test_validation_error():
    """ValidationError raises and is catchable with correct message."""
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError("Invalid paper_id")
    assert "Invalid paper_id" in str(exc_info.value)
    assert isinstance(exc_info.value, PipelineError)


def test_db_quality_graph_inherit():
    """DatabaseError, DataQualityError, GraphConstructionError inherit PipelineError."""
    assert issubclass(DatabaseError, PipelineError)
    assert issubclass(DataQualityError, PipelineError)
    assert issubclass(GraphConstructionError, PipelineError)
    assert str(DatabaseError("db")) == "db"


# ─── Aggressive / edge-case tests (all meaningful for real usage) ───────────

def test_rate_limit_catch_order():
    """RateLimitError is catchable as RateLimitError, APIError, PipelineError, Exception (catch order matters in code)."""
    e = RateLimitError("429 Too Many Requests")
    assert isinstance(e, RateLimitError)
    assert isinstance(e, APIError)
    assert isinstance(e, PipelineError)
    assert isinstance(e, Exception)
    # Simulate catch order: specific first
    caught = None
    try:
        raise e
    except RateLimitError as ex:
        caught = ("RateLimitError", ex)
    assert caught[0] == "RateLimitError"
    assert caught[1].args[0] == "429 Too Many Requests"


def test_validation_not_api():
    """ValidationError is PipelineError but not APIError (different branch of hierarchy)."""
    e = ValidationError("Invalid input")
    assert isinstance(e, PipelineError)
    assert not isinstance(e, APIError)
    assert isinstance(e, Exception)


def test_db_quality_graph_not_api():
    """DatabaseError and DataQualityError are pipeline errors but not API errors."""
    assert not isinstance(DatabaseError("x"), APIError)
    assert not isinstance(DataQualityError("x"), APIError)
    assert not isinstance(GraphConstructionError("x"), APIError)


def test_all_instantiable():
    """Every error type can be constructed with a message and str(e) preserves it."""
    msg = "something went wrong"
    for exc_cls in (PipelineError, APIError, RateLimitError, ValidationError, DatabaseError, DataQualityError, GraphConstructionError):
        e = exc_cls(msg)
        assert str(e) == msg
        assert e.args[0] == msg


def test_args_preserved():
    """Exception .args is set so logging and serialization work as expected."""
    e = ValidationError("Invalid paper_id: must be non-empty string")
    assert len(e.args) >= 1
    assert e.args[0] == "Invalid paper_id: must be non-empty string"


def test_validation_rerase_type():
    """Catching ValidationError and re-raising preserves the exception type (important for upstream handlers)."""
    try:
        try:
            raise ValidationError("bad value")
        except ValidationError as ex:
            assert str(ex) == "bad value"
            raise
    except ValidationError as ex2:
        assert str(ex2) == "bad value"
        assert type(ex2).__name__ == "ValidationError"
    else:
        pytest.fail("ValidationError should have been re-raised")


def test_api_caught_by_pipeline():
    """APIError (and thus RateLimitError) can be caught by except PipelineError in generic handlers."""
    for exc in (APIError("net"), RateLimitError("429")):
        caught = None
        try:
            raise exc
        except PipelineError as ex:
            caught = ex
        assert caught is not None
        assert isinstance(caught, PipelineError)
