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


class TestLazyImport:
    def test_httpx_not_in_qmt_gateway_module_globals(self):
        """NFR-0100: httpx should NOT appear in qmt_gateway module's global namespace."""
        import trader_off.broker.qmt_gateway as mod

        assert "httpx" not in dir(mod), (
            "httpx must not appear in qmt_gateway module-level namespace"
        )
