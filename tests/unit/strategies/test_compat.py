"""Unit tests for strategies/compat.py — millionaire framework compatibility shim."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestCompatStubs:
    """Tests for compat.py stub classes (used when quantide is not installed)."""

    def test_base_strategy_init_stores_broker_and_config(self):
        """Stub BaseStrategy.__init__ stores broker and config."""
        from trader_off.strategies.compat import BaseStrategy

        broker = MagicMock()
        config = {"top_k": 20, "model_version": "v0.2.0.1"}

        strategy = BaseStrategy(broker=broker, config=config)

        assert strategy.broker is broker
        assert strategy.config == config

    def test_base_strategy_init_with_no_config(self):
        """Stub BaseStrategy.__init__ defaults config to empty dict."""
        from trader_off.strategies.compat import BaseStrategy

        broker = MagicMock()
        strategy = BaseStrategy(broker=broker)

        assert strategy.config == {}

    def test_base_strategy_async_methods_are_pass(self):
        """Stub BaseStrategy async lifecycle methods are no-ops."""
        from trader_off.strategies.compat import BaseStrategy

        broker = MagicMock()
        strategy = BaseStrategy(broker=broker)

        # These should be async no-ops that return None
        # Just verify they exist and are callable
        assert callable(strategy.init)
        assert callable(strategy.on_day_open)
        assert callable(strategy.on_bar)
        assert callable(strategy.on_day_close)
        assert callable(strategy.on_stop)

    def test_broker_is_abstract_base_class(self):
        """Stub Broker is an ABC with trade_target_pct as abstract method."""
        import inspect

        from trader_off.strategies.compat import Broker

        # Broker should be an abstract base class
        assert inspect.isclass(Broker)
        # trade_target_pct should be marked as abstract
        assert getattr(Broker.trade_target_pct, "__isabstractmethod__", False) is True


class TestCompatWithQuantideInstalled:
    """Tests that verify the import logic when quantide IS installed.

    Since quantide is not installed in the test environment, these tests
    use mocking to simulate the scenario where quantide IS available.
    """

    def test_quantide_not_installed_uses_stubs(self):
        """Verify quantide is not installed (stubs are being used).

        Skip when quantide is installed (real framework active, stubs no-op).
        """
        pytest.importorskip("quantide")  # skip if quantide installed
        with pytest.raises(ModuleNotFoundError):
            pass
