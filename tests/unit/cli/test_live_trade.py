"""Unit tests for live-trade CLI (FR-0200)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from trader_off.cli.live_trade import main

# patch target for QmtGatewayBroker (imported at function scope per NFR-0100)
_BROKER_PATCH = "trader_off.broker.qmt_gateway.QmtGatewayBroker"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_universe_csv():
    """Create a temporary universe CSV with an asset column, return its Path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("asset\n000001.SZ\n600000.SH\n")
        return Path(f.name)


def _make_mock_broker(account_data=None, positions_data=None, orders_data=None, trades_data=None):
    """Create and return a MagicMock broker with default return values."""
    broker = MagicMock()
    broker.get_account.return_value = account_data or {"total_asset": 1000000.0}
    broker.get_positions.return_value = positions_data or []
    broker.get_orders.return_value = orders_data or []
    broker.get_trades.return_value = trades_data or []
    return broker


# ---------------------------------------------------------------------------
# Argument parsing tests
# ---------------------------------------------------------------------------


class TestArgParsing:
    def test_strategy_required(self):
        """--strategy is required."""
        result = main([])
        assert result == 2

    def test_universe_required(self):
        """--universe is required."""
        result = main(["--strategy", "optimized_topk"])
        assert result == 2

    def test_default_values(self):
        """Default --gateway-url, --capital, --api-key resolution."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker) as mock_broker_cls:
                result = main(["--strategy", "optimized_topk", "--universe", str(universe)])
                assert result == 0
                mock_broker_cls.assert_called_once_with(
                    base_url="http://localhost:5800", api_key=None
                )
                broker.set_principal.assert_called_once_with(1_000_000.0)
        finally:
            universe.unlink(missing_ok=True)

    def test_custom_gateway_url(self):
        """--gateway-url overrides default."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker) as mock_broker_cls:
                result = main(
                    [
                        "--strategy",
                        "optimized_topk",
                        "--universe",
                        str(universe),
                        "--gateway-url",
                        "http://192.168.1.100:5800",
                    ]
                )
                assert result == 0
                mock_broker_cls.assert_called_once_with(
                    base_url="http://192.168.1.100:5800", api_key=None
                )
        finally:
            universe.unlink(missing_ok=True)

    def test_gateway_api_key_from_arg(self):
        """--gateway-api-key is passed to broker."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker) as mock_broker_cls:
                result = main(
                    [
                        "--strategy",
                        "optimized_topk",
                        "--universe",
                        str(universe),
                        "--gateway-api-key",
                        "my-secret-key",
                    ]
                )
                assert result == 0
                mock_broker_cls.assert_called_once_with(
                    base_url="http://localhost:5800", api_key="my-secret-key"
                )
        finally:
            universe.unlink(missing_ok=True)

    def test_gateway_api_key_from_env(self, monkeypatch):
        """QMT_GATEWAY_KEY env var fallback works."""
        monkeypatch.setenv("QMT_GATEWAY_KEY", "env-secret-key")
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker) as mock_broker_cls:
                result = main(["--strategy", "optimized_topk", "--universe", str(universe)])
                assert result == 0
                mock_broker_cls.assert_called_once_with(
                    base_url="http://localhost:5800", api_key="env-secret-key"
                )
        finally:
            universe.unlink(missing_ok=True)

    def test_arg_api_key_takes_precedence_over_env(self, monkeypatch):
        """--gateway-api-key arg takes precedence over env var."""
        monkeypatch.setenv("QMT_GATEWAY_KEY", "env-key")
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker) as mock_broker_cls:
                result = main(
                    [
                        "--strategy",
                        "optimized_topk",
                        "--universe",
                        str(universe),
                        "--gateway-api-key",
                        "arg-key",
                    ]
                )
                assert result == 0
                mock_broker_cls.assert_called_once_with(
                    base_url="http://localhost:5800", api_key="arg-key"
                )
        finally:
            universe.unlink(missing_ok=True)

    def test_custom_capital(self):
        """--capital overrides default."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker):
                result = main(
                    [
                        "--strategy",
                        "optimized_topk",
                        "--universe",
                        str(universe),
                        "--capital",
                        "500000",
                    ]
                )
                assert result == 0
                broker.set_principal.assert_called_once_with(500000.0)
        finally:
            universe.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_universe_file_not_found(self):
        """Missing universe file returns exit code 3."""
        result = main(["--strategy", "optimized_topk", "--universe", "/nonexistent/file.csv"])
        assert result == 3

    def test_broker_connection_failure(self):
        """Gateway connection failure returns exit code 4."""
        universe = _make_universe_csv()
        try:
            broker = MagicMock()
            broker.set_principal.return_value = None
            broker.get_account.side_effect = RuntimeError("Connection refused")
            with patch(_BROKER_PATCH, return_value=broker):
                result = main(["--strategy", "optimized_topk", "--universe", str(universe)])
                assert result == 4
        finally:
            universe.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# JSON output tests
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_output_flag_produces_valid_json(self, capsys):
        """--json flag produces valid JSON on stdout."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker(
                account_data={"available_cash": 900000.0, "total_asset": 1100000.0},
                positions_data=[{"symbol": "000001.SZ", "shares": 1000}],
                orders_data=[{"qtoid": "123", "status": "filled"}],
                trades_data=[{"qtoid": "123", "price": 12.0}],
            )
            with patch(_BROKER_PATCH, return_value=broker):
                result = main(
                    [
                        "--strategy",
                        "optimized_topk",
                        "--universe",
                        str(universe),
                        "--json",
                    ]
                )
                assert result == 0

            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert output["strategy"] == "optimized_topk"
            assert output["capital"] == 1_000_000.0
            assert "account" in output
            assert "positions" in output
            assert "orders" in output
            assert "trades" in output
            assert output["account"]["total_asset"] == 1100000.0
            assert len(output["positions"]) == 1
        finally:
            universe.unlink(missing_ok=True)

    def test_default_text_output(self, capsys):
        """Default (non-JSON) output produces human-readable text."""
        universe = _make_universe_csv()
        try:
            broker = _make_mock_broker()
            with patch(_BROKER_PATCH, return_value=broker):
                result = main(["--strategy", "optimized_topk", "--universe", str(universe)])
                assert result == 0

            captured = capsys.readouterr()
            assert "Live Trade Summary" in captured.out
        finally:
            universe.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# NFR-0100 lazy import test
# ---------------------------------------------------------------------------


class TestLazyImport:
    def test_qmt_gateway_broker_not_at_module_level(self):
        """NFR-0100: QmtGatewayBroker should NOT be imported at module level."""
        import trader_off.cli.live_trade as mod

        assert "QmtGatewayBroker" not in dir(mod), (
            "QmtGatewayBroker must not appear in live_trade module-level namespace"
        )
