"""Unit tests for src.storage.gcs_client (GCSClient)."""
from unittest.mock import MagicMock, patch

import pytest


class TestGCSClient:
    @pytest.fixture
    def mock_gcs(self):
        with patch("src.storage.gcs_client._get_shared_client") as mock:
            client = MagicMock()
            bucket = MagicMock()
            client.bucket.return_value = bucket
            mock.return_value = client
            yield {"client": client, "bucket": bucket}

    def test_init_sets_bucket_and_prefix(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        gcs = GCSClient(bucket_name="test-bucket", prefix="test/")

        assert gcs.bucket_name == "test-bucket"
        assert gcs.prefix == "test/"

    def test_base_uri(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        gcs = GCSClient(bucket_name="mybucket", prefix="pdfs")

        assert gcs.base_uri == "gs://mybucket/pdfs/"

    def test_exists_calls_blob_exists(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        result = gcs.exists("paper123.pdf")

        assert result is True
        mock_gcs["bucket"].blob.assert_called()

    def test_upload_returns_uri(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.name = "p/paper.pdf"
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="test", prefix="p/")
        uri = gcs.upload("paper.pdf", b"%PDF-content", "application/pdf")

        assert "gs://test/" in uri
        blob.upload_from_string.assert_called_once()

    def test_download_returns_none_when_not_found(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        result = gcs.download("missing.pdf")

        assert result is None

    def test_exists_batch_returns_set(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob1 = MagicMock()
        blob1.name = "pdfs/a.pdf"
        blob2 = MagicMock()
        blob2.name = "pdfs/b.pdf"
        mock_gcs["client"].list_blobs.return_value = [blob1, blob2]

        gcs = GCSClient(bucket_name="b", prefix="pdfs/")
        existing = gcs.exists_batch(["a.pdf", "b.pdf", "c.pdf"])

        assert "a.pdf" in existing
        assert "b.pdf" in existing
        assert "c.pdf" not in existing

    def test_delete_returns_true_when_found(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        result = gcs.delete("found.pdf")

        assert result is True
        blob.delete.assert_called_once()

    def test_delete_returns_false_when_not_found(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        result = gcs.delete("missing.pdf")

        assert result is False
        blob.delete.assert_not_called()

    def test_delete_batch_returns_count(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        def make_blob(exists_val):
            blob = MagicMock()
            blob.exists.return_value = exists_val
            return blob

        mock_gcs["bucket"].blob.side_effect = [
            make_blob(True),
            make_blob(False),
            make_blob(True),
        ]

        gcs = GCSClient(bucket_name="b", prefix="p/")
        deleted = gcs.delete_batch(["a.pdf", "b.pdf", "c.pdf"])

        assert deleted == 2

    def test_list_files_returns_metadata(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        blob.size = 1024
        blob.updated = MagicMock()
        blob.updated.strftime.return_value = "2024-01-15 12:00:00"
        blob.metadata = {"source": "arxiv"}
        mock_gcs["client"].list_blobs.return_value = [blob]

        gcs = GCSClient(bucket_name="mybucket", prefix="pdfs/")
        files = gcs.list_files()

        assert len(files) == 1
        assert files[0]["filename"] == "paper.pdf"
        assert files[0]["size_bytes"] == 1024
        assert files[0]["size_mb"] == 0.0
        assert "gs://mybucket/" in files[0]["uri"]
        assert files[0]["metadata"] == {"source": "arxiv"}

    def test_upload_with_metadata_sets_blob_metadata(self, mock_gcs):
        from src.storage.gcs_client import GCSClient

        blob = MagicMock()
        blob.name = "p/paper.pdf"
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        gcs.upload("paper.pdf", b"content", metadata={"source": "arxiv"})

        assert blob.metadata == {"source": "arxiv"}
        blob.upload_from_string.assert_called_once()

    def test_download_to_file_returns_true_when_found(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        from pathlib import Path

        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        local_path = Path("/tmp/test_download.pdf")
        result = gcs.download_to_file("paper.pdf", local_path)

        assert result is True
        blob.download_to_filename.assert_called_once_with("/tmp/test_download.pdf")

    def test_download_to_file_returns_false_when_not_found(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        from pathlib import Path

        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        gcs = GCSClient(bucket_name="b", prefix="p/")
        result = gcs.download_to_file("missing.pdf", Path("/tmp/missing.pdf"))

        assert result is False
        blob.download_to_filename.assert_not_called()
