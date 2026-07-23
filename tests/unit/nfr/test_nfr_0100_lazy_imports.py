"""NFR-0100: Function-scope lazy imports for allowlisted modules.

Allowlist: httpx, qmt_gateway.* (not a Python package — external HTTP service).
These modules must NOT be imported at module level.
"""


class TestHttpxLazyImport:
    def test_httpx_not_in_qmt_gateway_module_globals(self):
        """httpx must not appear in qmt_gateway module-level namespace."""
        import trader_off.broker.qmt_gateway as mod

        assert "httpx" not in dir(mod), (
            "httpx must not appear in qmt_gateway module-level namespace"
        )

    def test_qmt_gateway_broker_not_in_live_trade_module_globals(self):
        """QmtGatewayBroker must not appear in live_trade module-level namespace."""
        import trader_off.cli.live_trade as mod

        assert "QmtGatewayBroker" not in dir(mod), (
            "QmtGatewayBroker must not appear in live_trade module-level namespace"
        )

    def test_httpx_imported_inside_qmt_gateway_method(self):
        """httpx is imported only inside method bodies of qmt_gateway.py."""
        import inspect

        import trader_off.broker.qmt_gateway as mod

        # httpx should appear inside _request method, not at module level
        source = inspect.getsource(mod.QmtGatewayBroker._request)
        assert "import httpx" in source, "httpx must be lazily imported inside _request method"
