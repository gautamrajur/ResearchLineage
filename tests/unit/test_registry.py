"""Unit tests for model registry and rollback."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_storage():
    """Mock Google Cloud Storage client."""
    with patch("src.registry.artifact_registry.storage") as mock:
        client = MagicMock()
        mock.Client.return_value = client
        bucket = MagicMock()
        client.bucket.return_value = bucket
        yield bucket


class TestPushModelToRegistry:
    def test_creates_metadata_entry(self, mock_storage):
        from src.registry.artifact_registry import push_model_to_registry

        blob = MagicMock()
        mock_storage.blob.return_value = blob

        result = push_model_to_registry(
            model_gcs_uri="gs://bucket/models/trained/v1",
            version="v1",
            metadata={"eval_score": 0.95},
        )

        assert "gs://" in result
        assert "v1" in result
        blob.upload_from_string.assert_called_once()

        # Verify the metadata content
        uploaded = blob.upload_from_string.call_args[0][0]
        import json
        data = json.loads(uploaded)
        assert data["version"] == "v1"
        assert data["model_gcs_uri"] == "gs://bucket/models/trained/v1"
        assert data["stage"] == "staging"
        assert data["eval_score"] == 0.95


class TestListModelVersions:
    def test_returns_sorted_versions(self, mock_storage):
        from src.registry.artifact_registry import list_model_versions

        blob1 = MagicMock()
        blob1.name = "model-registry/v1/metadata.json"
        blob1.download_as_text.return_value = '{"version": "v1", "registered_at": "2026-01-01"}'

        blob2 = MagicMock()
        blob2.name = "model-registry/v2/metadata.json"
        blob2.download_as_text.return_value = '{"version": "v2", "registered_at": "2026-02-01"}'

        mock_storage.list_blobs.return_value = [blob1, blob2]

        versions = list_model_versions()
        assert len(versions) == 2
        assert versions[0]["version"] == "v2"  # newer first


class TestPromoteModel:
    def test_updates_stage(self, mock_storage):
        from src.registry.artifact_registry import promote_model

        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_text.return_value = '{"version": "v1", "stage": "staging"}'
        mock_storage.blob.return_value = blob

        promote_model(version="v1", stage="production")

        blob.upload_from_string.assert_called_once()
        import json
        data = json.loads(blob.upload_from_string.call_args[0][0])
        assert data["stage"] == "production"
        assert "promoted_at" in data

    def test_raises_if_version_not_found(self, mock_storage):
        from src.registry.artifact_registry import promote_model

        blob = MagicMock()
        blob.exists.return_value = False
        mock_storage.blob.return_value = blob

        with pytest.raises(ValueError, match="not found"):
            promote_model(version="v999")


class TestRollbackModel:
    @patch("src.registry.rollback.storage")
    def test_dry_run_does_not_modify(self, mock_storage_mod):
        from src.registry.rollback import rollback_model

        client = MagicMock()
        mock_storage_mod.Client.return_value = client
        bucket = MagicMock()
        client.bucket.return_value = bucket
        bucket.list_blobs.return_value = [MagicMock()]  # model exists

        result = rollback_model(target_version="v1", dry_run=True)

        assert result["dry_run"] is True
        assert result["target_version"] == "v1"
        # Should not update pipeline_state.json
        bucket.blob.return_value.upload_from_string.assert_not_called()

    @patch("src.registry.rollback.storage")
    def test_raises_if_model_not_found(self, mock_storage_mod):
        from src.registry.rollback import rollback_model

        client = MagicMock()
        mock_storage_mod.Client.return_value = client
        bucket = MagicMock()
        client.bucket.return_value = bucket
        bucket.list_blobs.return_value = []  # model not found

        with pytest.raises(ValueError, match="not found"):
            rollback_model(target_version="v999")
