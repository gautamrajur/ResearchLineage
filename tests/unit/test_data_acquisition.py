"""Unit tests for DataAcquisitionTask — pure logic only, no real API calls."""
import pytest
from unittest.mock import patch

from src.utils.errors import ValidationError

# Import the module first so patch.object can reference it directly.
# This also verifies the module itself is importable (all deps present).
import src.tasks.data_acquisition as _acq_mod


@pytest.fixture
def task():
    """DataAcquisitionTask with all external clients mocked out."""
    with (
        patch.object(_acq_mod, "RedisCache"),
        patch.object(_acq_mod, "SemanticScholarClient"),
        patch.object(_acq_mod, "OpenAlexClient"),
        patch.object(_acq_mod, "IDMapper"),
    ):
        return _acq_mod.DataAcquisitionTask()


# ─── _validate_inputs ────────────────────────────────────────────────────────

class TestValidateInputs:
    def test_valid_inputs_pass(self, task):
        task._validate_inputs("abc123", 3, "backward")  # must not raise

    def test_empty_paper_id_raises(self, task):
        with pytest.raises(ValidationError, match="paper_id"):
            task._validate_inputs("", 3, "backward")

    def test_none_paper_id_raises(self, task):
        with pytest.raises(ValidationError, match="paper_id"):
            task._validate_inputs(None, 3, "backward")

    def test_depth_zero_raises(self, task):
        with pytest.raises(ValidationError, match="max_depth"):
            task._validate_inputs("abc", 0, "backward")

    def test_depth_above_five_raises(self, task):
        with pytest.raises(ValidationError, match="max_depth"):
            task._validate_inputs("abc", 6, "backward")

    def test_depth_five_is_valid(self, task):
        task._validate_inputs("abc", 5, "backward")  # boundary — must not raise

    def test_invalid_direction_raises(self, task):
        with pytest.raises(ValidationError, match="direction"):
            task._validate_inputs("abc", 3, "sideways")

    @pytest.mark.parametrize("direction", ["backward", "forward", "both"])
    def test_all_valid_directions(self, task, direction):
        task._validate_inputs("abc", 3, direction)  # must not raise


# ─── _validate_outputs ───────────────────────────────────────────────────────

class TestValidateOutputs:
    def test_valid_output_passes(self, task):
        result = {
            "target_paper_id": "abc",
            "papers": [{"paperId": "abc"}],
            "references": [],
            "citations": [],
        }
        task._validate_outputs(result)  # must not raise

    def test_missing_key_raises(self, task):
        with pytest.raises(ValidationError, match="papers"):
            task._validate_outputs({"target_paper_id": "abc", "references": [], "citations": []})

    def test_empty_papers_raises(self, task):
        with pytest.raises(ValidationError, match="No papers"):
            task._validate_outputs(
                {"target_paper_id": "abc", "papers": [], "references": [], "citations": []}
            )


# ─── _get_max_papers_for_depth ───────────────────────────────────────────────

class TestMaxPapersForDepth:
    @pytest.mark.parametrize("depth,expected", [(0, 5), (1, 5), (2, 3), (3, 2), (4, 2)])
    def test_depth_limits(self, task, depth, expected):
        # depth 0 and 1 map to settings.max_papers_per_level (default = 5)
        result = task._get_max_papers_for_depth(depth)
        assert result == expected


# ─── _filter_references_for_recursion ────────────────────────────────────────

class TestFilterReferences:
    def _make_ref(self, intents=None, is_influential=False, citation_count=100):
        return {
            "intents": intents or [],
            "isInfluential": is_influential,
            "citedPaper": {"paperId": "xyz", "citationCount": citation_count},
        }

    def test_methodology_intent_kept(self, task):
        refs = [self._make_ref(intents=["methodology"])]
        result = task._filter_references_for_recursion(refs, current_depth=0)
        assert len(result) == 1

    def test_background_intent_kept(self, task):
        refs = [self._make_ref(intents=["background"])]
        result = task._filter_references_for_recursion(refs, current_depth=0)
        assert len(result) == 1

    def test_influential_kept(self, task):
        refs = [self._make_ref(is_influential=True)]
        result = task._filter_references_for_recursion(refs, current_depth=0)
        assert len(result) == 1

    def test_irrelevant_intent_dropped(self, task):
        refs = [self._make_ref(intents=["result"])]
        result = task._filter_references_for_recursion(refs, current_depth=0)
        assert len(result) == 0

    def test_respects_depth_limit(self, task):
        # depth=3 → limit=2; provide 5 refs all with methodology intent
        refs = [self._make_ref(intents=["methodology"], citation_count=i * 100) for i in range(5)]
        result = task._filter_references_for_recursion(refs, current_depth=3)
        assert len(result) == 2

    def test_sorted_by_score_descending(self, task):
        high = self._make_ref(intents=["methodology"], citation_count=9000)
        low  = self._make_ref(intents=["background"],  citation_count=1)
        result = task._filter_references_for_recursion([low, high], current_depth=0)
        assert result[0]["citedPaper"]["citationCount"] == 9000


# ─── _filter_citations_for_recursion ─────────────────────────────────────────

class TestFilterCitations:
    def _make_cit(self, title="ML paper", intents=None, is_influential=False, citation_count=100):
        return {
            "intents": intents or ["methodology"],
            "isInfluential": is_influential,
            "citingPaper": {"paperId": "cite1", "title": title, "citationCount": citation_count},
        }

    def test_methodology_citation_kept(self, task):
        cits = [self._make_cit()]
        result = task._filter_citations_for_recursion(cits, {}, current_depth=0)
        assert len(result) == 1

    def test_medical_title_removed(self, task):
        cits = [self._make_cit(title="Lung Cancer Detection with Deep Learning")]
        result = task._filter_citations_for_recursion(cits, {}, current_depth=0)
        assert len(result) == 0

    def test_clinical_title_removed(self, task):
        cits = [self._make_cit(title="Clinical diagnosis of tumor")]
        result = task._filter_citations_for_recursion(cits, {}, current_depth=0)
        assert len(result) == 0

    def test_non_methodology_non_influential_dropped(self, task):
        cits = [self._make_cit(intents=["result"], is_influential=False)]
        result = task._filter_citations_for_recursion(cits, {}, current_depth=0)
        assert len(result) == 0

    def test_influential_kept_without_methodology(self, task):
        cits = [self._make_cit(intents=["result"], is_influential=True)]
        result = task._filter_citations_for_recursion(cits, {}, current_depth=0)
        assert len(result) == 1
