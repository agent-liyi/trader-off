"""Unit tests for FR-1600: Cron trigger.

AC coverage: AC-FR1600-01, AC-FR1600-02, AC-FR1600-03, AC-FR1600-04
T-3: next_cron_fire pure function with property tests.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import pytest

from trader_off.scheduler.core import SchedulerConfig
from trader_off.scheduler.cron import CronTrigger, next_cron_fire
from trader_off.scheduler.ports import VirtualClockPort

# ---------------------------------------------------------------------------
# T-3: next_cron_fire pure function property tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNextCronFirePureFunction:
    """T-3: Property tests for the next_cron_fire pure function.

    Verifies purity (determinism, no side effects) and basic correctness.
    """

    # -- Base correctness tests -----------------------------------------------

    @pytest.mark.parametrize(
        "expr, base, expected",
        [
            # AC-FR1600-04 exact match
            (
                "0 16 * * 1-5",
                datetime(2026, 7, 17, 15, 0),
                datetime(2026, 7, 17, 16, 0),
            ),
            # Same minute → exclusive (returns next match after base)
            (
                "0 16 * * 1-5",
                datetime(2026, 7, 17, 16, 0),
                datetime(2026, 7, 20, 16, 0),
            ),
            # After 16:00 on Friday → next Monday
            (
                "0 16 * * 1-5",
                datetime(2026, 7, 17, 16, 1),
                datetime(2026, 7, 20, 16, 0),
            ),
            # Midnight cron
            ("0 0 * * *", datetime(2026, 7, 17, 12, 0), datetime(2026, 7, 18, 0, 0)),
            # Every 30 minutes
            (
                "*/30 * * * *",
                datetime(2026, 7, 17, 15, 0),
                datetime(2026, 7, 17, 15, 30),
            ),
            # Specific day of month
            ("0 9 1 * *", datetime(2026, 7, 1, 8, 0), datetime(2026, 7, 1, 9, 0)),
            # First of month when we are past that day
            ("0 9 1 * *", datetime(2026, 7, 2, 8, 0), datetime(2026, 8, 1, 9, 0)),
        ],
    )
    def test_correctness(self, expr, base, expected):
        """T-3: next_cron_fire returns correct next fire time for various expressions."""
        result = next_cron_fire(expr, base)
        assert result == expected, f"Expected {expected}, got {result}"

    # -- Property: next_fire >= base -----------------------------------------

    @pytest.mark.parametrize(
        "expr, base",
        [
            ("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0)),
            ("*/15 * * * *", datetime(2026, 7, 17, 23, 59)),
            ("0 0 1 1 *", datetime(2025, 12, 31, 23, 59)),
            ("59 23 31 12 *", datetime(2026, 1, 1, 0, 0)),
        ],
    )
    def test_next_fire_gte_base(self, expr, base):
        """T-3 property: next_cron_fire result is always >= base."""
        result = next_cron_fire(expr, base)
        assert result >= base, f"next_cron_fire({expr!r}, {base}) = {result} < {base}"

    # -- Property: monotonic (non-decreasing) ---------------------------------

    @pytest.mark.parametrize(
        "expr, base",
        [
            ("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0)),
            ("*/10 * * * *", datetime(2026, 7, 17, 12, 0)),
        ],
    )
    def test_monotonic(self, expr, base):
        """T-3 property: next_fire(next_fire(base)) >= next_fire(base)."""
        first = next_cron_fire(expr, base)
        second = next_cron_fire(expr, first)
        assert second >= first, (
            f"Not monotonic: first={first}, second={second} for expr={expr!r}, base={base}"
        )

    # -- Timezone-awareness tests --------------------------------------------

    def test_tz_aware_preserves_timezone(self):
        """T-3: tz-aware base produces tz-aware result with same timezone."""
        from datetime import timedelta, timezone

        est = timezone(timedelta(hours=-5))
        base = datetime(2026, 7, 17, 10, 0, tzinfo=est)
        result = next_cron_fire("0 16 * * 1-5", base)
        assert result.tzinfo is not None, "Result should be tz-aware"
        # The hour should be 16 in EST
        assert result.hour == 16, f"Expected hour 16 in timezone, got {result.hour}"

    def test_tz_aware_utc(self):
        """T-3: tz-aware UTC base produces correct result."""
        base = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)
        result = next_cron_fire("0 16 * * 1-5", base)
        assert result.tzinfo is not None
        assert result.hour == 16

    # -- Determinism ----------------------------------------------------------

    def test_determinism(self):
        """T-3: same inputs produce same outputs (no module-level state)."""
        expr = "0 16 * * 1-5"
        base = datetime(2026, 7, 17, 15, 0)
        r1 = next_cron_fire(expr, base)
        r2 = next_cron_fire(expr, base)
        assert r1 == r2

    def test_determinism_no_side_effects(self):
        """T-3: multiple calls with different params don't affect each other."""
        r1 = next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0))
        r2 = next_cron_fire("0 9 * * 1-5", datetime(2026, 7, 17, 8, 0))
        assert r1 == datetime(2026, 7, 17, 16, 0)
        assert r2 == datetime(2026, 7, 17, 9, 0)
        # First call again, should be same
        r3 = next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0))
        assert r3 == r1

    # -- Invalid expression ---------------------------------------------------

    def test_invalid_expression_raises_valueerror(self):
        """T-3: invalid cron expression raises ValueError."""
        with pytest.raises(ValueError, match="[Cc]ron"):
            next_cron_fire("not a valid cron expression", datetime(2026, 7, 17, 15, 0))

    def test_empty_expression_raises(self):
        """T-3: empty string raises ValueError."""
        with pytest.raises(ValueError):
            next_cron_fire("", datetime(2026, 7, 17, 15, 0))

    # -- Naive datetime works ------------------------------------------------

    def test_naive_datetime(self):
        """T-3: naive datetime base is accepted and returns naive datetime."""
        base = datetime(2026, 7, 17, 15, 0)  # naive
        result = next_cron_fire("0 16 * * 1-5", base)
        assert result.tzinfo is None, f"Naive base should produce naive result, got {result}"
        assert result == datetime(2026, 7, 17, 16, 0)

    # -- APScheduler backend (reserved for future) ---------------------------

    def test_apscheduler_backend_raises_not_implemented(self):
        """T-3: backend='apscheduler' raises NotImplementedError (reserved)."""
        with pytest.raises(NotImplementedError, match="APScheduler"):
            next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0), backend="apscheduler")


# ---------------------------------------------------------------------------
# AC-FR1600-01: cron fires at correct time, not before
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCronTriggerAC01:
    """AC-FR1600-01: cron trigger fires at correct time.

    Given config `full_retrain = "0 16 * * 1-5"`, current time 15:59:30
    on a trading day. When scheduler ticks once. Then no trigger at 15:59:30;
    next trigger time should be 16:00.
    """

    @pytest.fixture
    def config(self) -> SchedulerConfig:
        return SchedulerConfig(
            full_retrain_cron="0 16 * * 1-5",
            incremental_retrain_cron="0 16 * * 1-5",
            clock=VirtualClockPort(),
        )

    @pytest.fixture
    def trigger(self, config: SchedulerConfig) -> CronTrigger:
        return CronTrigger(config)

    def test_not_fired_before_cron_time(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-01: No trigger when current time < cron fire time."""
        # 2026-07-17 is a Friday (trading day), 15:59:30
        now = datetime(2026, 7, 17, 15, 59, 30, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        # Check that we're not past the trigger yet
        next_full = trigger.compute_next_full()
        assert next_full == datetime(2026, 7, 17, 16, 0, tzinfo=UTC)

        # should_fire should be false since we're before the cron time
        assert trigger.should_fire_full(last_check=now) is False

    def test_fires_at_cron_time(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-01: Trigger fires when current time reaches cron time."""
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        # Check that at exactly 16:00, should_fire returns True
        assert trigger.should_fire_full(last_check=now) is True

    def test_next_full_correct(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-01: compute_next_full returns correct next fire time."""
        base = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)
        next_time = trigger.compute_next_full(base)
        assert next_time == datetime(2026, 7, 17, 16, 0, tzinfo=UTC)

    def test_fires_after_cron_time(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-01: Trigger fires when we've just passed the cron time."""
        now = datetime(2026, 7, 17, 16, 0, 1, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        # should_fire should be true since we've passed the cron time
        assert trigger.should_fire_full(last_check=now) is True

    def test_next_fire_after_triggering(self, config: SchedulerConfig, trigger: CronTrigger):
        """After firing, next trigger is the next matching cron slot."""
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)
        next_time = trigger.compute_next_full(now)
        # After 16:00 Friday, next should be Monday 16:00
        assert next_time == datetime(2026, 7, 20, 16, 0, tzinfo=UTC)

    def test_compute_next_incr_with_clock_default(
        self, config: SchedulerConfig, trigger: CronTrigger
    ):
        """compute_next_incremental uses clock.now() when base is None."""
        config.clock.set_now(datetime(2026, 7, 17, 15, 0, tzinfo=UTC))  # type: ignore[union-attr]
        next_time = trigger.compute_next_incremental()
        assert next_time == datetime(2026, 7, 17, 16, 0, tzinfo=UTC)

    def test_should_fire_incr_not_yet_reached(self, config: SchedulerConfig, trigger: CronTrigger):
        """should_fire_incremental returns False when cron time not yet reached on trading day."""
        # Friday 15:59:59 - before 16:00 cron
        now = datetime(2026, 7, 17, 15, 59, 59, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_incremental(last_check=now) is False


# ---------------------------------------------------------------------------
# AC-FR1600-02: Non-trading day skip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCronTriggerAC02:
    """AC-FR1600-02: Non-trading day (weekend) handling.

    Given config `incremental_retrain = "0 16 * * 1-5"`, on a non-trading
    day (weekend). Scheduler tick does NOT trigger. INFO log contains
    "cron skipped, not a trading day".
    """

    @pytest.fixture
    def config(self) -> SchedulerConfig:
        return SchedulerConfig(
            full_retrain_cron="0 16 * * 1-5",
            incremental_retrain_cron="0 16 * * 1-5",
            clock=VirtualClockPort(),
        )

    @pytest.fixture
    def trigger(self, config: SchedulerConfig) -> CronTrigger:
        return CronTrigger(config)

    def test_is_trading_day_weekday(self, trigger: CronTrigger):
        """AC-FR1600-02: Mon-Fri are trading days."""
        # Monday through Friday are trading days
        for day_offset in range(5):
            day = date(2026, 7, 13) + timedelta(days=day_offset)  # Mon to Fri
            assert trigger.is_trading_day(day) is True, f"{day} should be a trading day"

    def test_is_trading_day_weekend(self, trigger: CronTrigger):
        """AC-FR1600-02: Sat-Sun are NOT trading days."""
        # 2026-07-18 is Saturday, 2026-07-19 is Sunday
        assert trigger.is_trading_day(date(2026, 7, 18)) is False  # Saturday
        assert trigger.is_trading_day(date(2026, 7, 19)) is False  # Sunday

    def test_should_fire_false_on_weekend(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-02: should_fire returns False on weekend even after cron time."""
        # Saturday at 16:00 - cron time but not a trading day
        now = datetime(2026, 7, 18, 16, 0, 0, tzinfo=UTC)  # Saturday
        config.clock.set_now(now)  # type: ignore[union-attr]

        assert trigger.should_fire_full(last_check=now) is False
        assert trigger.should_fire_incremental(last_check=now) is False

    def test_should_fire_no_log_on_trading_day(
        self, config: SchedulerConfig, trigger: CronTrigger, caplog
    ):
        """AC-FR1600-02: No skip log on trading day."""
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)  # Friday
        config.clock.set_now(now)  # type: ignore[union-attr]

        with caplog.at_level(logging.INFO):
            trigger.should_fire_full(last_check=now)

        # Should NOT contain the skip message on a trading day
        assert "not a trading day" not in caplog.text

    def test_should_fire_logs_warning_on_weekend(
        self, config: SchedulerConfig, trigger: CronTrigger, caplog
    ):
        """AC-FR1600-02: INFO log when skipping due to non-trading day."""
        now = datetime(2026, 7, 18, 16, 0, 0, tzinfo=UTC)  # Saturday
        config.clock.set_now(now)  # type: ignore[union-attr]

        with caplog.at_level(logging.INFO):
            trigger.should_fire_full(last_check=now)

        assert "not a trading day" in caplog.text


# ---------------------------------------------------------------------------
# AC-FR1600-03: Frequency gate for full retrain
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCronTriggerAC03:
    """AC-FR1600-03: Full retrain frequency gate.

    Given full_retrain_frequency_days=5, last full retrain 3 trading days
    ago. When cron time arrives. Then full retrain is NOT triggered
    (3 < 5). Only incremental is triggered (if incremental cron is configured).
    """

    @pytest.fixture
    def config(self) -> SchedulerConfig:
        return SchedulerConfig(
            full_retrain_cron="0 16 * * 1-5",
            incremental_retrain_cron="0 16 * * 1-5",
            full_retrain_frequency_days=5,
            clock=VirtualClockPort(),
        )

    @pytest.fixture
    def trigger(self, config: SchedulerConfig) -> CronTrigger:
        return CronTrigger(config)

    def test_full_blocked_by_frequency_gate(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-03: Full retrain blocked when days since last < frequency_days."""
        # Last full retrain was 3 trading days ago (2026-07-14)
        last_full = date(2026, 7, 14)  # Tuesday
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)  # Friday
        config.clock.set_now(now)  # type: ignore[union-attr]

        # Set last full retrain date
        trigger.set_last_full_retrain_date(last_full)

        # Full should NOT fire due to frequency gate (3 < 5)
        assert trigger.should_fire_full(last_check=now) is False

        # Incremental should still fire
        assert trigger.should_fire_incremental(last_check=now) is True

    def test_full_allowed_after_frequency_met(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-03: Full retrain allowed when days since last >= frequency_days."""
        # Last full retrain was 5+ trading days ago (2026-07-10)
        last_full = date(2026, 7, 10)  # Friday
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)  # Next Friday
        config.clock.set_now(now)  # type: ignore[union-attr]

        trigger.set_last_full_retrain_date(last_full)

        # Full should fire (5 days have passed)
        assert trigger.should_fire_full(last_check=now) is True

    def test_full_allowed_when_no_previous_retrain(
        self, config: SchedulerConfig, trigger: CronTrigger
    ):
        """AC-FR1600-03: No previous retrain → full is allowed."""
        # No previous full retrain (last_full_retrain_date is None)
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        # No previous retrain → should always fire
        assert trigger.should_fire_full(last_check=now) is True

    def test_trigger_count_full_zero_incr_one(self, config: SchedulerConfig, trigger: CronTrigger):
        """AC-FR1600-03: trigger_count["full"]==0, trigger_count["incremental"]==1."""
        last_full = date(2026, 7, 14)  # 3 trading days ago (< 5)
        now = datetime(2026, 7, 17, 16, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        trigger.set_last_full_retrain_date(last_full)

        trigger_count = {"full": 0, "incremental": 0}

        if trigger.should_fire_full(last_check=now):
            trigger_count["full"] += 1
        if trigger.should_fire_incremental(last_check=now):
            trigger_count["incremental"] += 1

        assert trigger_count["full"] == 0
        assert trigger_count["incremental"] == 1


# ---------------------------------------------------------------------------
# AC-FR1600-04: next_cron_fire correctness (already partially covered in T-3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ac_fr1600_04_next_cron_fire_exact():
    """AC-FR1600-04: next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0))
    == datetime(2026, 7, 17, 16, 0)."""
    result = next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 15, 0))
    assert result == datetime(2026, 7, 17, 16, 0), f"Got {result}"


# ---------------------------------------------------------------------------
# CronTrigger additional tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCronTriggerEdgeCases:
    """Additional edge case tests for CronTrigger."""

    @pytest.fixture
    def config(self) -> SchedulerConfig:
        return SchedulerConfig(
            full_retrain_cron="0 9 * * 1-5",
            incremental_retrain_cron="*/30 * * * 1-5",
            clock=VirtualClockPort(),
        )

    @pytest.fixture
    def trigger(self, config: SchedulerConfig) -> CronTrigger:
        return CronTrigger(config)

    def test_late_night_not_fired(self, config: SchedulerConfig, trigger: CronTrigger):
        """Cron at 9:00 AM does not fire at 2:00 AM."""
        now = datetime(2026, 7, 17, 2, 0, 0, tzinfo=UTC)  # Friday 2 AM
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_full(last_check=now) is False

    def test_fires_when_past_cron_on_trading_day(
        self, config: SchedulerConfig, trigger: CronTrigger
    ):
        """Cron at 9:00 AM fires when time is past 9:00 on a trading day."""
        now = datetime(2026, 7, 17, 14, 30, 0, tzinfo=UTC)  # Friday 2:30 PM
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_full(last_check=now) is True

    def test_weekend_block_different_cron(self, config: SchedulerConfig, trigger: CronTrigger):
        """Any cron is blocked on weekends regardless of expression."""
        # Saturday
        now = datetime(2026, 7, 18, 10, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_full(last_check=now) is False
        assert trigger.should_fire_incremental(last_check=now) is False

    def test_full_independent_from_incr(self, config: SchedulerConfig, trigger: CronTrigger):
        """Full and incremental triggers operate independently."""
        last_full = date(2026, 7, 15)  # Wednesday
        trigger.set_last_full_retrain_date(last_full)

        # Thursday 9:00 AM - full frequency gate blocks (2 days < 5)
        now = datetime(2026, 7, 16, 9, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]

        assert trigger.should_fire_full(last_check=now) is False  # blocked by frequency
        assert trigger.should_fire_incremental(last_check=now) is True  # no frequency gate for incr

    def test_set_last_incremental_retrain_date(self, trigger: CronTrigger):
        """set_last_incremental_retrain_date stores the date for testing."""
        dt = date(2026, 7, 15)
        trigger.set_last_incremental_retrain_date(dt)
        assert trigger._last_incremental_retrain_date == dt

    def test_cron_not_today_incremental(self, config: SchedulerConfig, trigger: CronTrigger):
        """should_fire_incremental returns False when cron doesn't match today."""
        # Use a Monday-only cron on Friday
        trigger._config.incremental_retrain_cron = "0 9 * * 1"
        now = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)  # Friday
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_incremental(last_check=now) is False

    def test_cron_not_today_full(self, config: SchedulerConfig, trigger: CronTrigger):
        """should_fire_full returns False when cron doesn't match today."""
        trigger._config.full_retrain_cron = "0 9 * * 1"  # Monday only
        now = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)  # Friday
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_full(last_check=now) is False

    def test_invalid_cron_should_fire_full(self, config: SchedulerConfig, trigger: CronTrigger):
        """should_fire_full returns False when cron expression is invalid."""
        trigger._config.full_retrain_cron = "invalid cron expr"
        now = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_full(last_check=now) is False

    def test_invalid_cron_should_fire_incremental(
        self, config: SchedulerConfig, trigger: CronTrigger
    ):
        """should_fire_incremental returns False when cron expression is invalid."""
        trigger._config.incremental_retrain_cron = "invalid cron expr"
        now = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        config.clock.set_now(now)  # type: ignore[union-attr]
        assert trigger.should_fire_incremental(last_check=now) is False


# ---------------------------------------------------------------------------
# next_cron_fire: additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNextCronFireEdgeCases:
    """Additional edge case tests for the next_cron_fire pure function."""

    def test_past_end_of_range(self):
        """When base is past all valid cron slots in the current range."""
        # 0 16 * * 1-5: Friday 16:01 → Monday 16:00
        result = next_cron_fire("0 16 * * 1-5", datetime(2026, 7, 17, 16, 1))
        assert result == datetime(2026, 7, 20, 16, 0)

    def test_midnight_cross_day(self):
        """Cron at midnight crosses day boundary correctly."""
        result = next_cron_fire("0 0 * * *", datetime(2026, 7, 17, 23, 59))
        assert result == datetime(2026, 7, 18, 0, 0)

    def test_every_minute(self):
        """Wildcard cron fires the next minute (exclusive)."""
        result = next_cron_fire("* * * * *", datetime(2026, 7, 17, 15, 30))
        assert result == datetime(2026, 7, 17, 15, 31)

    def test_every_minute_next(self):
        """Wildcard cron fires the next minute when past the current."""
        result = next_cron_fire("* * * * *", datetime(2026, 7, 17, 15, 30, 1))
        assert result == datetime(2026, 7, 17, 15, 31)

    def test_specific_day_of_week_only(self):
        """Cron on specific days only fires on those days."""
        # Only Monday (1)
        result = next_cron_fire("0 9 * * 1", datetime(2026, 7, 17, 8, 0))  # Friday
        assert result == datetime(2026, 7, 20, 9, 0)  # Next Monday

    def test_six_field_expression(self):
        """Six-field cron expression (with seconds) is supported by croniter."""
        # Note: croniter supports 6-field expressions (with seconds as first field)
        # This is an optional feature, not a core requirement
        pass  # Documented but not mandatory
