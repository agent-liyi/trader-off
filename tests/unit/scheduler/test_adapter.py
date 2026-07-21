"""Tests for QuantideSchedulerAdapter — FR-0200."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ADAPTER_PATH = Path("src/trader_off/scheduler/adapter.py")


class TestQuantideSchedulerAdapterExists:
    """FR-0200: adapter module exists and exports expected interface."""

    def test_adapter_module_imports(self):
        """Adapter module can be imported."""
        from trader_off.scheduler.adapter import QuantideSchedulerAdapter

        assert QuantideSchedulerAdapter is not None

    def test_adapter_has_expected_methods(self):
        """Adapter exposes init, start, stop, add_job, add_listener."""
        from trader_off.scheduler.adapter import QuantideSchedulerAdapter

        adapter = QuantideSchedulerAdapter()
        assert hasattr(adapter, "init")
        assert hasattr(adapter, "start")
        assert hasattr(adapter, "stop")
        assert hasattr(adapter, "add_job")
        assert hasattr(adapter, "add_listener")

    def test_adapter_methods_are_callable(self):
        """All adapter methods are callable."""
        from trader_off.scheduler.adapter import QuantideSchedulerAdapter

        adapter = QuantideSchedulerAdapter()
        assert callable(adapter.init)
        assert callable(adapter.start)
        assert callable(adapter.stop)
        assert callable(adapter.add_job)
        assert callable(adapter.add_listener)


class TestQuantideSchedulerAdapterInit:
    """FR-0200: adapter.init() wraps SchedulerManager.init()."""

    def test_init_calls_scheduler_manager_init(self):
        """init() delegates to SchedulerManager.init() with timezone."""
        mock_sm = MagicMock()
        mock_sm._scheduler = None
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            adapter = QuantideSchedulerAdapter()
            adapter.init(timezone="Asia/Shanghai")

            mock_sm.init.assert_called_once_with(timezone="Asia/Shanghai")

    def test_init_is_idempotent(self):
        """Calling init twice does not double-initialize."""
        mock_sm = MagicMock()
        mock_sm._scheduler = None
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            adapter = QuantideSchedulerAdapter()
            adapter.init()
            adapter.init()
            assert mock_sm.init.call_count == 1


class TestQuantideSchedulerAdapterStartStop:
    """FR-0200: adapter.start()/stop() wrap SchedulerManager.start()/stop()."""

    def test_start_calls_scheduler_manager_start(self):
        """start() delegates to SchedulerManager.start()."""
        mock_sm = MagicMock()
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            adapter = QuantideSchedulerAdapter()
            adapter.start()

            mock_sm.start.assert_called_once()

    def test_stop_calls_scheduler_manager_stop(self):
        """stop() delegates to SchedulerManager.stop()."""
        mock_sm = MagicMock()
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            adapter = QuantideSchedulerAdapter()
            adapter.stop()

            mock_sm.stop.assert_called_once()


class TestQuantideSchedulerAdapterAddJob:
    """FR-0200: adapter.add_job() wraps SchedulerManager.add_job()."""

    def test_add_job_delegates(self):
        """add_job passes all arguments through to SchedulerManager."""
        mock_sm = MagicMock()
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            def dummy_func():
                pass

            adapter = QuantideSchedulerAdapter()
            adapter.add_job(dummy_func, trigger="cron", args=(1,), id="test")

            mock_sm.add_job.assert_called_once_with(
                dummy_func, trigger="cron", args=(1,), id="test"
            )


class TestQuantideSchedulerAdapterAddListener:
    """FR-0200: adapter.add_listener() wraps SchedulerManager.add_listener()."""

    def test_add_listener_delegates(self):
        """add_listener passes callback and mask through."""
        mock_sm = MagicMock()
        with patch(
            "trader_off.scheduler.adapter._get_scheduler_manager",
            return_value=mock_sm,
        ):
            from trader_off.scheduler.adapter import QuantideSchedulerAdapter

            def dummy_callback(event):
                pass

            adapter = QuantideSchedulerAdapter()
            adapter.add_listener(dummy_callback, mask=1)

            mock_sm.add_listener.assert_called_once_with(dummy_callback, mask=1)


class TestNFR0101FunctionScopeImports:
    """NFR-0101: all quantide imports in adapter are inside function bodies."""

    def test_no_top_level_quantide_import(self):
        """adapter.py has no top-level import from quantide."""
        if not ADAPTER_PATH.exists():
            pytest.skip("adapter.py not created yet")

        source = ADAPTER_PATH.read_text()
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("quantide"):
                        pytest.fail(f"Top-level quantide import found: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("quantide"):
                    pytest.fail(f"Top-level quantide import found: from {node.module} import ...")

    def test_quantide_imports_in_function_bodies(self):
        """All quantide imports are inside function/class bodies."""
        if not ADAPTER_PATH.exists():
            pytest.skip("adapter.py not created yet")

        source = ADAPTER_PATH.read_text()
        tree = ast.parse(source)

        def check_node(node, in_function=False):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                in_function = True

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("quantide") and not in_function:
                        pytest.fail(f"quantide import outside function body: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("quantide") and not in_function:
                    pytest.fail(f"quantide import outside function body: from {node.module}")

            for child in ast.iter_child_nodes(node):
                check_node(child, in_function)

        check_node(tree)

    def test_adapter_no_quantide_import_at_class_level(self):
        """Quantide imports must not be at class body level (only function bodies)."""
        if not ADAPTER_PATH.exists():
            pytest.skip("adapter.py not created yet")

        source = ADAPTER_PATH.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.Import) and not isinstance(
                        child, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        for alias in child.names:
                            if alias.name.startswith("quantide"):
                                pytest.fail("quantide import at class level in adapter.py")
                    elif isinstance(child, ast.ImportFrom) and not isinstance(
                        child, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        if child.module and child.module.startswith("quantide"):
                            pytest.fail("quantide import at class level in adapter.py")
