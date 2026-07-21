"""Tests for convert_fixture_to_quantide.py — FR-0300."""

import subprocess
from pathlib import Path

import polars as pl

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES_V020 = Path("tests/fixtures/v0.2.0")
FIXTURES_V030 = Path("tests/fixtures/v0.3.0")
CONVERT_SCRIPT = SCRIPTS_DIR / "convert_fixture_to_quantide.py"
OHLCV_50x252 = FIXTURES_V020 / "ohlcv_50x252.parquet"
OHLCV_10x60 = Path("tests/e2e/fixtures/ohlcv_10x60.parquet")


def _run_convert(args: list[str]) -> subprocess.CompletedProcess:
    """Run conversion script and return CompletedProcess."""
    return subprocess.run(
        ["uv", "run", "python", str(CONVERT_SCRIPT)] + args,
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestConvertFixtureScript:
    """FR-0300: fixture conversion script tests."""

    # AC-FR0300-01: exit 0, produce year-partitioned parquet
    def test_convert_50x252_exit_zero(self):
        """Converting ohlcv_50x252 exits 0 and produces partition files."""
        result = _run_convert(["--fixture", "ohlcv_50x252"])

        assert result.returncode == 0, f"Exit code {result.returncode}, stderr: {result.stderr}"

        store = FIXTURES_V030 / "daily_bars_store"
        assert store.exists(), f"daily_bars_store not created at {store}"
        parquet_files = list(store.rglob("*.parquet"))
        assert len(parquet_files) > 0, "No parquet files produced"

    # AC-FR0300-02: correct schema with date, asset, open, high, low, close, volume, adj_factor
    def test_output_schema(self):
        """Output parquet has correct flat columns."""
        # Assumes conversion was run (by test_convert_50x252_exit_zero)
        _run_convert(["--fixture", "ohlcv_50x252"])

        store = FIXTURES_V030 / "daily_bars_store"
        first_parquet = next(store.rglob("*.parquet"))
        df = pl.read_parquet(first_parquet)

        required_cols = {"date", "asset", "open", "high", "low", "close", "volume", "adj_factor"}
        missing = required_cols - set(df.columns)
        assert missing == set(), f"Missing columns: {missing}"

    # AC-FR0300-03: row count preserved
    def test_row_count_preserved(self):
        """Row count matches original fixture."""
        _run_convert(["--fixture", "ohlcv_50x252"])

        original = pl.read_parquet(OHLCV_50x252)
        store = FIXTURES_V030 / "daily_bars_store"
        all_rows = pl.concat([pl.read_parquet(f) for f in store.rglob("*.parquet")])
        assert len(all_rows) == len(original), f"Expected {len(original)} rows, got {len(all_rows)}"

    # AC-FR0300-04: excluded columns not present
    def test_excluded_columns_absent(self):
        """turnover, limit_up, limit_down are not in output."""
        _run_convert(["--fixture", "ohlcv_50x252"])

        store = FIXTURES_V030 / "daily_bars_store"
        first_parquet = next(store.rglob("*.parquet"))
        df = pl.read_parquet(first_parquet)

        for col in ["turnover", "limit_up", "limit_down"]:
            assert col not in df.columns, f"Column {col} should be excluded"

    # AC-FR0300-06: nonexistent input → exit 2
    def test_nonexistent_input_exit_2(self):
        """Nonexistent input file exits 2."""
        result = _run_convert(["--input", "/nonexistent/path.parquet"])
        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}. stderr: {result.stderr}"
        )
        assert "input file not found" in result.stderr.lower(), (
            f"Expected error message, got: {result.stderr}"
        )

    # AC-FR0300-07: schema mismatch → exit 3
    def test_schema_mismatch_exit_3(self, tmp_path):
        """Input with wrong schema exits 3."""
        bad_file = tmp_path / "bad_schema.parquet"
        pl.DataFrame({"x": [1, 2, 3]}).write_parquet(bad_file)

        result = _run_convert(["--input", str(bad_file)])
        assert result.returncode == 3, (
            f"Expected exit 3, got {result.returncode}. stderr: {result.stderr}"
        )
        assert "schema" in result.stderr.lower(), f"Expected schema error, got: {result.stderr}"

    # AC-FR0300-08: idempotent
    def test_idempotent_conversion(self):
        """Re-running produces same files (idempotent)."""
        store = FIXTURES_V030 / "daily_bars_store"

        import shutil

        if store.exists():
            shutil.rmtree(store)

        _run_convert(["--fixture", "ohlcv_50x252"])
        files_first = sorted(store.rglob("*.parquet"))
        hashes_first = {str(f): f.stat().st_size for f in files_first}

        _run_convert(["--fixture", "ohlcv_50x252"])
        files_second = sorted(store.rglob("*.parquet"))
        hashes_second = {str(f): f.stat().st_size for f in files_second}

        assert hashes_first == hashes_second, "Files differ between runs"
