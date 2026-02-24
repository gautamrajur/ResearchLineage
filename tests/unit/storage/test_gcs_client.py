"""Unit tests for src.storage.gcs_client."""
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import pytest


@pytest.fixture
def mock_gcs():
    """Mock GCS client and bucket."""
    with patch("src.storage.gcs_client._get_shared_client") as mock:
        client = MagicMock()
        bucket = MagicMock()
        client.bucket.return_value = bucket
        mock.return_value = client
        yield {"client": client, "bucket": bucket}


@pytest.fixture
def gcs(mock_gcs):
    """GCSClient instance with mocked backend."""
    from src.storage.gcs_client import GCSClient
    return GCSClient(bucket_name="test-bucket", prefix="pdfs/")


# ═══════════════════════════════════════════════════════════════════════════
# Init & Properties
# ═══════════════════════════════════════════════════════════════════════════


class TestInit:

    def test_sets_bucket_prefix(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        gcs = GCSClient(bucket_name="mybucket", prefix="files/")

        assert gcs.bucket_name == "mybucket"
        assert gcs.prefix == "files/"

    def test_normalizes_prefix(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        gcs = GCSClient(bucket_name="b", prefix="pdfs")  # No trailing slash

        assert gcs.prefix == "pdfs/"

    def test_base_uri(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        gcs = GCSClient(bucket_name="mybucket", prefix="pdfs/")

        assert gcs.base_uri == "gs://mybucket/pdfs/"

    def test_env_defaults(self, mock_gcs):
        from src.storage.gcs_client import GCSClient
        with patch.dict("os.environ", {"GCS_BUCKET": "env-bucket", "GCS_PREFIX": "env/"}):
            gcs = GCSClient()
            assert gcs.bucket_name == "env-bucket"
            assert gcs.prefix == "env/"


# ═══════════════════════════════════════════════════════════════════════════
# exists
# ═══════════════════════════════════════════════════════════════════════════


class TestExists:

    def test_true(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        assert gcs.exists("paper.pdf") is True
        mock_gcs["bucket"].blob.assert_called_with("pdfs/paper.pdf")

    def test_false(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        assert gcs.exists("missing.pdf") is False


# ═══════════════════════════════════════════════════════════════════════════
# upload
# ═══════════════════════════════════════════════════════════════════════════


class TestUpload:

    def test_returns_uri(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        mock_gcs["bucket"].blob.return_value = blob

        uri = gcs.upload("paper.pdf", b"%PDF-content", "application/pdf")

        assert uri == "gs://test-bucket/pdfs/paper.pdf"
        blob.upload_from_string.assert_called_once_with(b"%PDF-content", content_type="application/pdf")

    def test_with_metadata(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        mock_gcs["bucket"].blob.return_value = blob

        gcs.upload("paper.pdf", b"content", metadata={"source": "arxiv"})

        assert blob.metadata == {"source": "arxiv"}

    def test_no_metadata(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        blob.metadata = None
        mock_gcs["bucket"].blob.return_value = blob

        gcs.upload("paper.pdf", b"content")

        # metadata should not be set
        assert blob.metadata is None


# ═══════════════════════════════════════════════════════════════════════════
# download
# ═══════════════════════════════════════════════════════════════════════════


class TestDownload:

    def test_found(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_bytes.return_value = b"%PDF-content"
        mock_gcs["bucket"].blob.return_value = blob

        result = gcs.download("paper.pdf")

        assert result == b"%PDF-content"

    def test_not_found(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        assert gcs.download("missing.pdf") is None


# ═══════════════════════════════════════════════════════════════════════════
# download_to_file
# ═══════════════════════════════════════════════════════════════════════════


class TestDownloadToFile:

    def test_found(self, gcs, mock_gcs, tmp_path):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        local = tmp_path / "paper.pdf"
        result = gcs.download_to_file("paper.pdf", local)

        assert result is True
        blob.download_to_filename.assert_called_once()

    def test_not_found(self, gcs, mock_gcs, tmp_path):
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        result = gcs.download_to_file("missing.pdf", tmp_path / "out.pdf")

        assert result is False
        blob.download_to_filename.assert_not_called()

    def test_creates_parent_dirs(self, gcs, mock_gcs, tmp_path):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        # Nested path that doesn't exist
        local = tmp_path / "nested" / "dir" / "paper.pdf"
        gcs.download_to_file("paper.pdf", local)

        # Parent should be created
        assert local.parent.exists()


# ═══════════════════════════════════════════════════════════════════════════
# delete
# ═══════════════════════════════════════════════════════════════════════════


class TestDelete:

    def test_found(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        assert gcs.delete("paper.pdf") is True
        blob.delete.assert_called_once()

    def test_not_found(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        assert gcs.delete("missing.pdf") is False
        blob.delete.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# exists_batch
# ═══════════════════════════════════════════════════════════════════════════


class TestExistsBatch:

    def test_returns_existing(self, gcs, mock_gcs):
        blob_a = MagicMock()
        blob_a.name = "pdfs/a.pdf"
        blob_b = MagicMock()
        blob_b.name = "pdfs/b.pdf"

        blobs = [blob_a, blob_b]
        
        mock_gcs["client"].list_blobs.return_value = blobs

        existing = gcs.exists_batch(["a.pdf", "b.pdf", "c.pdf"])

        assert existing == {"a.pdf", "b.pdf"}
        assert "c.pdf" not in existing

    def test_empty_input(self, gcs, mock_gcs):
        mock_gcs["client"].list_blobs.return_value = []

        existing = gcs.exists_batch([])

        assert existing == set()

    def test_none_exist(self, gcs, mock_gcs):
        mock_gcs["client"].list_blobs.return_value = []

        existing = gcs.exists_batch(["a.pdf", "b.pdf"])

        assert existing == set()


# ═══════════════════════════════════════════════════════════════════════════
# delete_batch
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteBatch:

    def test_returns_count(self, gcs, mock_gcs):
        def make_blob(exists):
            b = MagicMock()
            b.exists.return_value = exists
            return b

        mock_gcs["bucket"].blob.side_effect = [
            make_blob(True),
            make_blob(False),
            make_blob(True),
        ]

        count = gcs.delete_batch(["a.pdf", "b.pdf", "c.pdf"])

        assert count == 2

    def test_empty_list(self, gcs, mock_gcs):
        assert gcs.delete_batch([]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# delete_all
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteAll:

    def test_deletes_all(self, gcs, mock_gcs):
        blobs = [MagicMock(), MagicMock(), MagicMock()]
        mock_gcs["client"].list_blobs.return_value = blobs

        count = gcs.delete_all()

        assert count == 3
        for b in blobs:
            b.delete.assert_called_once()

    def test_empty_bucket(self, gcs, mock_gcs):
        mock_gcs["client"].list_blobs.return_value = []

        assert gcs.delete_all() == 0


# ═══════════════════════════════════════════════════════════════════════════
# list_files
# ═══════════════════════════════════════════════════════════════════════════


class TestListFiles:

    def test_returns_metadata(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        blob.size = 2048
        blob.updated = MagicMock()
        blob.updated.strftime.return_value = "2024-01-15 12:00:00"
        blob.metadata = {"source": "arxiv"}
        mock_gcs["client"].list_blobs.return_value = [blob]

        files = gcs.list_files()

        assert len(files) == 1
        f = files[0]
        assert f["filename"] == "paper.pdf"
        assert f["size_bytes"] == 2048
        assert f["size_mb"] == 0.0
        assert f["uploaded"] == "2024-01-15 12:00:00"
        assert f["uri"] == "gs://test-bucket/pdfs/paper.pdf"
        assert f["metadata"] == {"source": "arxiv"}

    def test_empty(self, gcs, mock_gcs):
        mock_gcs["client"].list_blobs.return_value = []

        assert gcs.list_files() == []

    def test_skips_prefix_only(self, gcs, mock_gcs):
        """Skips blob where filename after prefix removal is empty."""
        blob = MagicMock()
        blob.name = "pdfs/"  # Just the prefix
        mock_gcs["client"].list_blobs.return_value = [blob]

        files = gcs.list_files()

        assert files == []

    def test_no_updated(self, gcs, mock_gcs):
        """Handles blob with no updated timestamp."""
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        blob.size = 1024
        blob.updated = None
        blob.metadata = None
        mock_gcs["client"].list_blobs.return_value = [blob]

        files = gcs.list_files()

        assert files[0]["uploaded"] == "unknown"

    def test_no_metadata(self, gcs, mock_gcs):
        """Handles blob with no metadata."""
        blob = MagicMock()
        blob.name = "pdfs/paper.pdf"
        blob.size = 1024
        blob.updated = MagicMock()
        blob.updated.strftime.return_value = "2024-01-01"
        blob.metadata = None
        mock_gcs["client"].list_blobs.return_value = [blob]

        files = gcs.list_files()

        assert files[0]["metadata"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# open_locally
# ═══════════════════════════════════════════════════════════════════════════


class TestOpenLocally:

    def test_not_found(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs["bucket"].blob.return_value = blob

        result = gcs.open_locally("missing.pdf")

        assert result is None

    def test_found_downloads(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        with patch("subprocess.run") as mock_run:
            with patch("platform.system", return_value="Darwin"):
                result = gcs.open_locally("paper.pdf")

        assert result is not None
        assert result.name == "paper.pdf"
        mock_run.assert_called_once()

    def test_linux(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        with patch("subprocess.run") as mock_run:
            with patch("platform.system", return_value="Linux"):
                gcs.open_locally("paper.pdf")

        args = mock_run.call_args[0][0]
        assert args[0] == "xdg-open"

    def test_windows(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        with patch("os.startfile", create=True) as mock_start:
            with patch("platform.system", return_value="Windows"):
                gcs.open_locally("paper.pdf")

        mock_start.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_unicode_filename(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.exists.return_value = True
        mock_gcs["bucket"].blob.return_value = blob

        gcs.exists("日本語.pdf")

        mock_gcs["bucket"].blob.assert_called_with("pdfs/日本語.pdf")

    def test_special_chars_filename(self, gcs, mock_gcs):
        blob = MagicMock()
        blob.name = "pdfs/file with spaces.pdf"
        mock_gcs["bucket"].blob.return_value = blob

        gcs.upload("file with spaces.pdf", b"content")

        mock_gcs["bucket"].blob.assert_called_with("pdfs/file with spaces.pdf")

    def test_large_file_size_mb(self, gcs, mock_gcs):
        """Large file size_mb calculation."""
        blob = MagicMock()
        blob.name = "pdfs/large.pdf"
        blob.size = 50 * 1024 * 1024  # 50 MB
        blob.updated = MagicMock()
        blob.updated.strftime.return_value = "2024-01-01"
        blob.metadata = {}
        mock_gcs["client"].list_blobs.return_value = [blob]

        files = gcs.list_files()

        assert files[0]["size_mb"] == 50.0

    def test_blob_path_construction(self, gcs, mock_gcs):
        """Verifies _blob_path adds prefix correctly."""
        blob = MagicMock()
        mock_gcs["bucket"].blob.return_value = blob

        gcs.exists("test.pdf")

        mock_gcs["bucket"].blob.assert_called_with("pdfs/test.pdf")
