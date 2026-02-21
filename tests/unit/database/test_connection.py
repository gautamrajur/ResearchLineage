"""Unit tests for src.database.connection (DatabaseConnection) with mocked engine."""
from unittest.mock import MagicMock, patch

import pytest


class TestDatabaseConnection:
    def test_get_session_yields_session_and_commits_on_success(self):
        with patch("src.database.connection.create_engine") as mock_engine_fn:
            with patch("src.database.connection.sessionmaker") as mock_sessionmaker:
                mock_session = MagicMock()
                mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

                # Reset singleton so we get our mocked engine
                import src.database.connection as conn_mod
                conn_mod.DatabaseConnection._instance = None
                conn_mod.DatabaseConnection._engine = None
                conn_mod.DatabaseConnection._SessionLocal = None

                conn = conn_mod.DatabaseConnection()

                with conn.get_session() as session:
                    assert session is mock_session

                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    def test_get_session_rolls_back_on_exception(self):
        with patch("src.database.connection.create_engine"):
            with patch("src.database.connection.sessionmaker") as mock_sessionmaker:
                mock_session = MagicMock()
                mock_session.commit.side_effect = RuntimeError("DB error")
                mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

                import src.database.connection as conn_mod
                conn_mod.DatabaseConnection._instance = None
                conn_mod.DatabaseConnection._engine = None
                conn_mod.DatabaseConnection._SessionLocal = None

                conn = conn_mod.DatabaseConnection()

                with pytest.raises(RuntimeError, match="DB error"):
                    with conn.get_session() as session:
                        pass

                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()

    def test_singleton_returns_same_instance(self):
        with patch("src.database.connection.create_engine"):
            with patch("src.database.connection.sessionmaker"):
                import src.database.connection as conn_mod
                conn_mod.DatabaseConnection._instance = None
                conn_mod.DatabaseConnection._engine = None
                conn_mod.DatabaseConnection._SessionLocal = None

                c1 = conn_mod.DatabaseConnection()
                c2 = conn_mod.DatabaseConnection()
                assert c1 is c2
