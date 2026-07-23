"""Unit tests for QmtGatewayBroker (FR-0100).

Tests use httpx mocks to simulate qmt-gateway HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from trader_off.broker.qmt_gateway import QmtGatewayBroker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code=200, json_data=None, text=""):
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _setup_mock_client(mock_client, response):
    """Configure the mocked httpx.Client instance to return `response` on request().

    Must set __enter__.return_value to mock_client itself because the
    implementation uses `with self._get_client() as client:`.
    """
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = response


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_base_url(self):
        """Default base_url is http://localhost:5800."""
        broker = QmtGatewayBroker()
        assert broker.base_url == "http://localhost:5800"

    def test_custom_base_url(self):
        """Custom base_url is accepted."""
        broker = QmtGatewayBroker(base_url="http://192.168.1.100:5800")
        assert broker.base_url == "http://192.168.1.100:5800"

    def test_base_url_trailing_slash_stripped(self):
        """Trailing slashes are stripped from base_url."""
        broker = QmtGatewayBroker(base_url="http://localhost:5800/")
        assert broker.base_url == "http://localhost:5800"

    def test_invalid_base_url_raises_value_error(self):
        """Invalid URL format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid base_url"):
            QmtGatewayBroker(base_url="not-a-valid-url")

    def test_api_key_stored(self):
        """API key is stored when provided."""
        broker = QmtGatewayBroker(api_key="secret123")
        assert broker.api_key == "secret123"

    def test_api_key_none_by_default(self):
        """API key defaults to None."""
        broker = QmtGatewayBroker()
        assert broker.api_key is None


# ---------------------------------------------------------------------------
# login tests
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_accepts_credentials(self):
        """login stores username/password for later use."""
        broker = QmtGatewayBroker()
        broker.login("user", "pass")
        assert broker._username == "user"
        assert broker._password == "pass"


# ---------------------------------------------------------------------------
# GET endpoint tests (using httpx mock)
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    @pytest.fixture
    def mock_client(self):
        """Fixture that patches httpx.Client to return a mock."""
        with patch("httpx.Client") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    def test_get_account(self, mock_client):
        """GET /asset returns parsed JSON account info."""
        expected = {
            "available_cash": 1000000.0,
            "total_asset": 1100000.0,
            "frozen_cash": 0.0,
        }
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_account()

        mock_client.request.assert_called_once_with("GET", "/asset", params=None)
        assert result == expected

    def test_get_positions(self, mock_client):
        """GET /positions returns parsed JSON positions list."""
        expected = [
            {"symbol": "000001.SZ", "shares": 1000, "market_value": 12000.0},
        ]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_positions()

        mock_client.request.assert_called_once_with("GET", "/positions", params=None)
        assert result == expected

    def test_get_orders_default_status(self, mock_client):
        """GET /orders?status=all by default."""
        expected = [{"qtoid": "123", "status": "filled"}]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_orders()

        mock_client.request.assert_called_once_with("GET", "/orders", params={"status": "all"})
        assert result == expected

    def test_get_orders_custom_status(self, mock_client):
        """GET /orders?status=pending returns pending orders."""
        expected = [{"qtoid": "456", "status": "pending"}]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_orders(status="pending")

        mock_client.request.assert_called_once_with("GET", "/orders", params={"status": "pending"})
        assert result == expected

    def test_get_trades(self, mock_client):
        """GET /trades returns parsed JSON trades list."""
        expected = [{"qtoid": "123", "symbol": "000001.SZ", "price": 12.0}]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_trades()

        mock_client.request.assert_called_once_with("GET", "/trades", params=None)
        assert result == expected

    def test_get_connection_status(self, mock_client):
        """GET /connection_status returns connection state dict."""
        expected = {"connected": True, "qmt_version": "2.0"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_connection_status()

        mock_client.request.assert_called_once_with("GET", "/connection_status", params=None)
        assert result == expected

    def test_search_stocks(self, mock_client):
        """GET /search_stocks?q=keyword returns matching stock list."""
        expected = [{"symbol": "000001.SZ", "name": "平安银行"}]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.search_stocks("平安")

        mock_client.request.assert_called_once_with("GET", "/search_stocks", params={"q": "平安"})
        assert result == expected

    def test_get_stock_info(self, mock_client):
        """GET /stock_info?symbol=000001.SZ returns stock detail dict."""
        expected = {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "sector": "银行",
        }
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_stock_info("000001.SZ")

        mock_client.request.assert_called_once_with(
            "GET", "/stock_info", params={"symbol": "000001.SZ"}
        )
        assert result == expected

    def test_get_all_stocks(self, mock_client):
        """GET /all_stocks returns full stock list."""
        expected = [
            {"symbol": "000001.SZ", "name": "平安银行"},
            {"symbol": "600000.SH", "name": "浦发银行"},
        ]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_all_stocks()

        mock_client.request.assert_called_once_with("GET", "/all_stocks", params=None)
        assert result == expected

    def test_get_minutes_job(self, mock_client):
        """GET /minutes_job/{job_id} returns download progress."""
        expected = {"job_id": "abc123", "progress": 75, "status": "downloading"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_minutes_job("abc123")

        mock_client.request.assert_called_once_with("GET", "/minutes_job/abc123", params=None)
        assert result == expected

    def test_get_quote_status(self, mock_client):
        """GET /quote_status returns WebSocket subscription status."""
        expected = {"subscribed": True, "symbols": ["000001.SZ"]}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_quote_status()

        mock_client.request.assert_called_once_with("GET", "/quote_status", params=None)
        assert result == expected

    def test_get_auction_status(self, mock_client):
        """GET /auction_status returns auction session status."""
        expected = {"is_auction_time": True, "phase": "closing_call"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_auction_status()

        mock_client.request.assert_called_once_with("GET", "/auction_status", params=None)
        assert result == expected


# ---------------------------------------------------------------------------
# POST endpoint tests
# ---------------------------------------------------------------------------


class TestPostEndpoints:
    @pytest.fixture
    def mock_client(self):
        with patch("httpx.Client") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    def test_buy(self, mock_client):
        """POST /buy_stock sends correct params and returns parsed JSON."""
        expected = {"qtoid": "order-001", "status": "submitted"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.buy("000001.SZ", 12.5, 100)

        mock_client.request.assert_called_once_with(
            "POST",
            "/buy_stock",
            params={"symbol": "000001.SZ", "price": 12.5, "shares": 100, "qtoid": ""},
        )
        assert result == expected

    def test_buy_with_qtoid(self, mock_client):
        """POST /buy_stock includes qtoid when provided."""
        expected = {"qtoid": "my-id", "status": "submitted"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.buy("000001.SZ", 12.5, 100, qtoid="my-id")

        mock_client.request.assert_called_once_with(
            "POST",
            "/buy_stock",
            params={
                "symbol": "000001.SZ",
                "price": 12.5,
                "shares": 100,
                "qtoid": "my-id",
            },
        )
        assert result == expected

    def test_sell(self, mock_client):
        """POST /sell_stock sends correct params and returns parsed JSON."""
        expected = {"qtoid": "order-002", "status": "submitted"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.sell("600000.SH", 15.0, 200)

        mock_client.request.assert_called_once_with(
            "POST",
            "/sell_stock",
            params={
                "symbol": "600000.SH",
                "price": 15.0,
                "shares": 200,
                "qtoid": "",
            },
        )
        assert result == expected

    def test_sell_with_qtoid(self, mock_client):
        """POST /sell_stock includes qtoid when provided."""
        expected = {"qtoid": "my-id-2", "status": "submitted"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.sell("600000.SH", 15.0, 200, qtoid="my-id-2")

        mock_client.request.assert_called_once_with(
            "POST",
            "/sell_stock",
            params={
                "symbol": "600000.SH",
                "price": 15.0,
                "shares": 200,
                "qtoid": "my-id-2",
            },
        )
        assert result == expected

    def test_cancel_order(self, mock_client):
        """POST /cancel_order sends qtoid param."""
        expected = {"qtoid": "order-003", "status": "cancelled"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.cancel_order("order-003")

        mock_client.request.assert_called_once_with(
            "POST",
            "/cancel_order",
            params={"qtoid": "order-003"},
        )
        assert result == expected

    def test_set_principal(self, mock_client):
        """POST /update_principal sends principal param."""
        expected = {"status": "ok", "principal": 2000000.0}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.set_principal(2000000.0)

        mock_client.request.assert_called_once_with(
            "POST",
            "/update_principal",
            params={"principal": 2000000.0},
        )
        assert result == expected

    def test_restart_qmt(self, mock_client):
        """POST /restart_qmt sends password param and returns status dict."""
        expected = {"status": "restarting", "message": "QMT restart initiated"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.restart_qmt("my-secret")

        mock_client.request.assert_called_once_with(
            "POST",
            "/restart_qmt",
            params={"password": "my-secret"},
        )
        assert result == expected

    def test_download_minutes(self, mock_client):
        """POST /download_minutes sends comma-joined dates and returns job info."""
        expected = {"job_id": "job-001", "status": "started"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.download_minutes(["2024-01-02", "2024-01-03"])

        mock_client.request.assert_called_once_with(
            "POST",
            "/download_minutes",
            params={"dates": "2024-01-02,2024-01-03"},
        )
        assert result == expected

    def test_download_minutes_single_date(self, mock_client):
        """POST /download_minutes with single date still sends comma-joined string."""
        expected = {"job_id": "job-002", "status": "started"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.download_minutes(["2024-01-02"])

        mock_client.request.assert_called_once_with(
            "POST",
            "/download_minutes",
            params={"dates": "2024-01-02"},
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.fixture
    def mock_client(self):
        with patch("httpx.Client") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    def test_http_error_raises_runtime_error(self, mock_client):
        """Non-200 status raises RuntimeError with status code and message."""
        _setup_mock_client(
            mock_client,
            _mock_response(status_code=500, text="Internal Server Error"),
        )

        broker = QmtGatewayBroker()
        with pytest.raises(RuntimeError, match="500.*Internal Server Error"):
            broker.get_account()

    def test_client_error_raises_runtime_error(self, mock_client):
        """4xx status raises RuntimeError with status code and message."""
        _setup_mock_client(
            mock_client,
            _mock_response(status_code=404, text="Not Found"),
        )

        broker = QmtGatewayBroker()
        with pytest.raises(RuntimeError, match="404.*Not Found"):
            broker.get_account()

    def test_network_error_raises_runtime_error(self, mock_client):
        """Network/timeout exception is wrapped in RuntimeError."""
        from httpx import RequestError

        mock_client.__enter__.return_value = mock_client
        mock_client.request.side_effect = RequestError("Connection refused")

        broker = QmtGatewayBroker()
        with pytest.raises(RuntimeError, match="Request failed.*Connection refused"):
            broker.get_account()


# ---------------------------------------------------------------------------
# NFR-0100 lazy import tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# P2: System management endpoint tests (FR-0100)
# ---------------------------------------------------------------------------


class TestSystemEndpoints:
    @pytest.fixture
    def mock_client(self):
        with patch("httpx.Client") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    # --- GET /api/system/version ---

    def test_get_version(self, mock_client):
        """GET /api/system/version returns parsed JSON version info."""
        expected = {"version": "1.2.3", "build": "2024-01-01"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_version()

        mock_client.request.assert_called_once_with("GET", "/api/system/version", params=None)
        assert result == expected

    # --- POST /api/system/version/check ---

    def test_check_version(self, mock_client):
        """POST /api/system/version/check returns version check result."""
        expected = {"up_to_date": False, "latest": "1.2.4"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.check_version()

        mock_client.request.assert_called_once_with(
            "POST", "/api/system/version/check", params=None
        )
        assert result == expected

    # --- POST /api/system/update ---

    def test_start_update(self, mock_client):
        """POST /api/system/update triggers update and returns status."""
        expected = {"status": "updating", "message": "Update started"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.start_update()

        mock_client.request.assert_called_once_with("POST", "/api/system/update", params=None)
        assert result == expected

    # --- GET /api/system/update/status/{task_id} ---

    def test_get_update_status(self, mock_client):
        """GET /api/system/update/status/{task_id} returns update progress."""
        expected = {"task_id": "task-001", "progress": 50, "status": "downloading"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_update_status("task-001")

        mock_client.request.assert_called_once_with(
            "GET", "/api/system/update/status/task-001", params=None
        )
        assert result == expected

    # --- POST /api/system/rollback ---

    def test_do_rollback(self, mock_client):
        """POST /api/system/rollback triggers rollback and returns status."""
        expected = {"status": "rolled_back", "message": "Rollback complete"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.do_rollback()

        mock_client.request.assert_called_once_with("POST", "/api/system/rollback", params=None)
        assert result == expected

    # --- GET /api/system/autostart ---

    def test_get_autostart(self, mock_client):
        """GET /api/system/autostart returns current autostart config."""
        expected = {"enabled": True}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_autostart()

        mock_client.request.assert_called_once_with("GET", "/api/system/autostart", params=None)
        assert result == expected

    # --- POST /api/system/autostart (form data) ---

    def test_set_autostart_enabled(self, mock_client):
        """POST /api/system/autostart with data enabled=true enables autostart."""
        expected = {"status": "ok", "enabled": True}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.set_autostart(True)

        mock_client.request.assert_called_once_with(
            "POST",
            "/api/system/autostart",
            params=None,
            data={"enabled": "true"},
        )
        assert result == expected

    def test_set_autostart_disabled(self, mock_client):
        """POST /api/system/autostart with data enabled=false disables autostart."""
        expected = {"status": "ok", "enabled": False}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.set_autostart(False)

        mock_client.request.assert_called_once_with(
            "POST",
            "/api/system/autostart",
            params=None,
            data={"enabled": "false"},
        )
        assert result == expected

    # --- GET /api/system/port ---

    def test_get_port(self, mock_client):
        """GET /api/system/port returns current gateway port."""
        expected = {"port": 5800}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_port()

        mock_client.request.assert_called_once_with("GET", "/api/system/port", params=None)
        assert result == expected

    # --- GET /api/system/firewall ---

    def test_get_firewall(self, mock_client):
        """GET /api/system/firewall returns current firewall rules."""
        expected = {"rules": [{"ip": "192.168.1.0/24", "action": "allow"}]}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.get_firewall()

        mock_client.request.assert_called_once_with("GET", "/api/system/firewall", params=None)
        assert result == expected

    # --- POST /api/system/firewall (form data) ---

    def test_update_firewall(self, mock_client):
        """POST /api/system/firewall sends form data with port rules."""
        rules = [{"ip": "10.0.0.0/8", "action": "allow"}]
        expected = {"status": "ok", "rules": rules}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.update_firewall(rules)

        mock_client.request.assert_called_once_with(
            "POST",
            "/api/system/firewall",
            params=None,
            data={"port": rules},
        )
        assert result == expected


# ---------------------------------------------------------------------------
# P2: API key management endpoint tests (FR-0100)
# ---------------------------------------------------------------------------


class TestApiKeyEndpoints:
    @pytest.fixture
    def mock_client(self):
        with patch("httpx.Client") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    # --- POST /api/api-keys (form data) ---

    def test_create_api_key(self, mock_client):
        """POST /api/api-keys with form data creates a new API key."""
        expected = {"id": "key-001", "name": "my-app", "key": "sk-xxxx"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.create_api_key("my-app")

        mock_client.request.assert_called_once_with(
            "POST",
            "/api/api-keys",
            params=None,
            data={"name": "my-app"},
        )
        assert result == expected

    # --- GET /api/api-keys ---

    def test_list_api_keys(self, mock_client):
        """GET /api/api-keys returns list of API keys."""
        expected = [
            {"id": "key-001", "name": "my-app", "created_at": "2024-01-01"},
            {"id": "key-002", "name": "other-app", "created_at": "2024-01-02"},
        ]
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.list_api_keys()

        mock_client.request.assert_called_once_with("GET", "/api/api-keys", params=None)
        assert result == expected

    # --- DELETE /api/api-keys/{key_id} ---

    def test_revoke_api_key(self, mock_client):
        """DELETE /api/api-keys/{key_id} revokes an API key."""
        expected = {"status": "revoked", "id": "key-001"}
        _setup_mock_client(mock_client, _mock_response(json_data=expected))

        broker = QmtGatewayBroker()
        result = broker.revoke_api_key("key-001")

        mock_client.request.assert_called_once_with(
            "DELETE",
            "/api/api-keys/key-001",
            params=None,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# NFR-0100 lazy import tests
# ---------------------------------------------------------------------------


class TestLazyImport:
    def test_httpx_not_in_qmt_gateway_module_globals(self):
        """NFR-0100: httpx should NOT appear in qmt_gateway module's global namespace."""
        import trader_off.broker.qmt_gateway as mod

        assert "httpx" not in dir(mod), (
            "httpx must not appear in qmt_gateway module-level namespace"
        )
