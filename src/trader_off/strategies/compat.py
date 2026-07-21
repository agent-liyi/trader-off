"""Millionaire framework compatibility shim.

Provides stub BaseStrategy and Broker classes when the `quantide` package
(millionaire framework) is not installed. In production, the real millionaire
classes are used.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

try:
    from quantide.core.strategy import BaseStrategy  # type: ignore[import-untyped]
    from quantide.service.base_broker import Broker  # type: ignore[import-untyped]
except ImportError:

    class BaseStrategy(ABC):  # type: ignore[no-redef]
        """Stub BaseStrategy matching millionaire's interface.

        When millionaire is installed, the real quantide.core.strategy.BaseStrategy
        is used instead via the try/except ImportError above.
        """

        def __init__(self, broker: Any, config: dict | None = None):
            """Initialize strategy.

            Args:
                broker: Broker instance for order execution.
                config: Strategy configuration dict.
            """
            self.broker = broker
            self.config = config or {}

        async def init(self) -> None:
            """Initialize strategy state. Called once before trading starts."""
            pass

        async def on_day_open(self, tm: datetime) -> None:
            """Called at the start of each trading day."""
            pass

        async def on_bar(
            self,
            tm: datetime,
            quote: dict[str, Any] | None = None,
            frame_type=None,
        ) -> None:
            """Called on each bar/period update.

            Args:
                tm: Current bar timestamp.
                quote: Quote data dict keyed by asset.
                frame_type: Bar frame type (e.g., FrameType.DAY).
            """
            pass

        async def on_day_close(self, tm: datetime) -> None:
            """Called at the end of each trading day."""
            pass

        async def on_stop(self) -> None:
            """Called when backtest/trading ends for cleanup."""
            pass

    class Broker(ABC):  # type: ignore[no-redef]
        """Stub Broker matching millionaire's interface."""

        @abstractmethod
        async def trade_target_pct(
            self,
            asset: str,
            target_pct: float,
        ) -> None:
            """Set target portfolio percentage for an asset."""
            ...
