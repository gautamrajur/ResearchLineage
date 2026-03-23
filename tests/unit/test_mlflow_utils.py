"""Unit tests for MLflow utilities."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_mlflow():
    """Mock MLflow module to avoid needing a running server."""
    with patch("src.mlflow_utils.mlflow") as mock:
        mock.get_experiment_by_name.return_value = MagicMock(experiment_id="1")
        run_mock = MagicMock()
        run_mock.info.run_id = "test-run-123"
        mock.start_run.return_value.__enter__ = MagicMock(return_value=run_mock)
        mock.start_run.return_value.__exit__ = MagicMock(return_value=False)
        yield mock


@pytest.fixture
def mock_client():
    """Mock MlflowClient."""
    with patch("src.mlflow_utils.MlflowClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        yield client


class TestGetOrCreateExperiment:
    def test_returns_existing_experiment_id(self, mock_mlflow):
        from src.mlflow_utils import get_or_create_experiment

        result = get_or_create_experiment("test-exp")
        assert result == "1"
        mock_mlflow.get_experiment_by_name.assert_called_once_with("test-exp")

    def test_creates_experiment_if_not_found(self, mock_mlflow):
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "2"
        from src.mlflow_utils import get_or_create_experiment

        result = get_or_create_experiment("new-exp")
        assert result == "2"
        mock_mlflow.create_experiment.assert_called_once_with("new-exp")


class TestLogTrainingRun:
    def test_logs_params_and_metrics(self, mock_mlflow):
        from src.mlflow_utils import log_training_run

        run_id = log_training_run(
            params={"lr": 0.001, "epochs": 3},
            metrics={"loss": 0.5, "accuracy": 0.9},
            model_uri="gs://bucket/model/v1",
            tags={"version": "v1"},
        )
        assert run_id == "test-run-123"
        mock_mlflow.log_params.assert_called_once()
        mock_mlflow.log_metrics.assert_called_once()


class TestLogEvaluationRun:
    def test_logs_eval_metrics(self, mock_mlflow):
        from src.mlflow_utils import log_evaluation_run

        run_id = log_evaluation_run(
            eval_metrics={"predecessor_accuracy": 0.85, "judge_overall_mean": 3.5},
            model_version="v1",
        )
        assert run_id == "test-run-123"
        mock_mlflow.log_metrics.assert_called_once()


class TestLogBiasReport:
    def test_logs_bias_metrics(self, mock_mlflow):
        from src.mlflow_utils import log_bias_report

        run_id = log_bias_report(
            bias_metrics={"accuracy_disparity": 0.05, "judge_disparity": 0.3},
            model_version="v1",
            passed=True,
        )
        assert run_id == "test-run-123"
        mock_mlflow.set_tag.assert_any_call("bias_check_passed", "True")


class TestRegisterModel:
    def test_registers_new_version(self, mock_mlflow, mock_client):
        from src.mlflow_utils import register_model

        version_mock = MagicMock(version="1")
        mock_client.create_model_version.return_value = version_mock

        result = register_model(
            run_id="test-run-123",
            model_uri="gs://bucket/model/v1",
            model_name="test-model",
        )
        assert result.version == "1"
        mock_client.create_model_version.assert_called_once()


class TestGetLatestProductionModel:
    def test_returns_latest_version(self, mock_mlflow, mock_client):
        from src.mlflow_utils import get_latest_production_model

        v1 = MagicMock(version="1")
        v2 = MagicMock(version="2")
        mock_client.search_model_versions.return_value = [v1, v2]

        result = get_latest_production_model("test-model")
        assert result.version == "2"

    def test_returns_none_when_no_versions(self, mock_mlflow, mock_client):
        from src.mlflow_utils import get_latest_production_model

        mock_client.search_model_versions.return_value = []

        result = get_latest_production_model("test-model")
        assert result is None
