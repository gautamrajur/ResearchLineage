"""Unit tests for src.cache.redis_client (RedisCache)."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestRedisCache:
    @pytest.fixture
    def mock_redis(self):
        with patch("src.cache.redis_client.redis.Redis") as mock:
            client = MagicMock()
            client.ping.return_value = True
            mock.return_value = client
            yield client

    def test_init_connects_successfully(self, mock_redis):
        from src.cache.redis_client import RedisCache

        cache = RedisCache()

        mock_redis.ping.assert_called_once()

    def test_get_returns_parsed_json(self, mock_redis):
        from src.cache.redis_client import RedisCache

        mock_redis.get.return_value = '{"key": "value"}'

        cache = RedisCache()
        result = cache.get("test_key")

        assert result == {"key": "value"}

    def test_get_returns_none_when_missing(self, mock_redis):
        from src.cache.redis_client import RedisCache

        mock_redis.get.return_value = None

        cache = RedisCache()
        result = cache.get("missing")

        assert result is None

    def test_set_serializes_and_stores(self, mock_redis):
        from src.cache.redis_client import RedisCache

        cache = RedisCache()
        cache.set("key", {"data": 123}, ttl=3600)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "key"
        assert call_args[0][1] == 3600
        assert json.loads(call_args[0][2]) == {"data": 123}

    def test_delete_calls_redis_delete(self, mock_redis):
        from src.cache.redis_client import RedisCache

        cache = RedisCache()
        cache.delete("key")

        mock_redis.delete.assert_called_with("key")

    def test_operations_return_false_or_none_when_disconnected(self):
        from src.cache.redis_client import RedisCache

        with patch("src.cache.redis_client.redis") as mock_redis_mod:
            mock_redis_mod.ConnectionError = Exception
            mock_redis_mod.Redis.return_value.ping.side_effect = Exception(
                "Connection failed"
            )

            cache = RedisCache()

            assert cache.client is None
            assert cache.get("key") is None
            assert cache.set("key", "value") is False
            assert cache.delete("key") is False
