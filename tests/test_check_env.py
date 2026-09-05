from unittest.mock import patch
from scripts.check_env import run_checks, check_tcp_port, check_http_endpoint


def test_check_tcp_port():
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = True
        assert check_tcp_port("localhost", 5432) is True

    with patch("socket.create_connection", side_effect=OSError):
        assert check_tcp_port("localhost", 5432) is False


def test_run_checks():
    with patch("scripts.check_env.check_tcp_port", return_value=True), \
         patch("scripts.check_env.check_http_endpoint", return_value=True):
        results = run_checks()
        assert results["PostgreSQL"] is True
        assert results["Redis"] is True
        assert results["Qdrant"] is True
        assert results["Ollama"] is True
