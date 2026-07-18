"""Unit tests for scheduler/ports.py — Protocol stubs and edge cases."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trader_off.scheduler.ports import (
    ClockPort,
    SystemClockPort,
    TrainerPort,
    VirtualClockPort,
)


class TestVirtualClockPort:
    """Tests for VirtualClockPort — T-1 testability seam."""

    def test_set_now_updates_time(self):
        """set_now() changes the clock's notion of now."""
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        clock = VirtualClockPort(start=start)

        new_time = datetime(2026, 7, 15, 12, 30, 0, tzinfo=UTC)
        clock.set_now(new_time)

        assert clock.now() == new_time

    def test_advance_moves_time_forward(self):
        """advance(seconds) adds to the current time."""
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        clock = VirtualClockPort(start=start)

        clock.advance(3600)  # 1 hour

        expected = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
        assert clock.now() == expected

    def test_default_start_is_2026_01_01(self):
        """Default start time is 2026-01-01 00:00:00 UTC."""
        clock = VirtualClockPort()
        assert clock.now() == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestSystemClockPort:
    """Tests for SystemClockPort — T-1 default implementation."""

    def test_now_returns_tz_aware_utc(self):
        """now() returns a timezone-aware UTC datetime."""
        clock = SystemClockPort()
        result = clock.now()

        # AC-FR1500-01: SystemClockPort must produce tz-aware UTC datetimes
        assert result.tzinfo is not None
        assert result.tzinfo == UTC


class TestClockPortProtocol:
    """Smoke tests that ClockPort Protocol can be used as a type annotation."""

    def test_clock_port_protocol_exists(self):
        """ClockPort is a valid Protocol class."""
        assert hasattr(ClockPort, "__protocol_attrs__")

    def test_trainer_port_protocol_exists(self):
        """TrainerPort is a valid Protocol class."""
        assert hasattr(TrainerPort, "__protocol_attrs__")

    def test_virtual_clock_satisfies_clock_port_protocol(self):
        """VirtualClockPort has the required 'now' method for ClockPort protocol."""
        clock: ClockPort = VirtualClockPort()
        # ClockPort protocol requires a 'now' method - verify it exists
        assert hasattr(clock, "now")
        assert callable(clock.now)
        # Verify it returns a datetime
        result = clock.now()
        assert isinstance(result, datetime)


class TestDefaultTrainerPortUnknownMode:
    """Line 233: DefaultTrainerPort.train() raises ValueError for unknown mode."""

    @pytest.mark.asyncio
    async def test_train_raises_on_unknown_mode(self):
        """Unknown mode string raises ValueError with informative message."""
        from trader_off.scheduler.ports import DefaultTrainerPort

        port = DefaultTrainerPort(models_dir=Path("/tmp/test"))

        with pytest.raises(ValueError, match="Unknown training mode"):
            await port.train(mode="invalid_mode")
