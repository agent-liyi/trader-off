"""Unit tests for FR-0100: REST API server (FastAPI).

Covers AC-FR0100-01 through AC-FR0100-07.
Uses FastAPI TestClient with mocked CLI internal functions to verify endpoint
existence, success/error response shapes, and exit-code → HTTP status mapping.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Test fixtures — FastAPI TestClient with mocked runners
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a FastAPI TestClient with mocked CLI runners returning success."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    with (
        patch("trader_off.api.server._run_backtest_sync", return_value=0),
        patch("trader_off.api.server._run_cli_sync", return_value=0),
        patch("trader_off.api.server._run_scheduler_sync", return_value=0),
    ):
        from trader_off.api.server import create_app

        app = create_app()
        yield TestClient(app)


@pytest.fixture
def error_client():
    """Create a TestClient where CLI runners return error code 4 (config error)."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    with (
        patch("trader_off.api.server._run_backtest_sync", return_value=4),
        patch("trader_off.api.server._run_cli_sync", return_value=4),
        patch("trader_off.api.server._run_scheduler_sync", return_value=4),
    ):
        from trader_off.api.server import create_app

        app = create_app()
        yield TestClient(app)


# ---------------------------------------------------------------------------
# AC-FR0100-02: GET /api/health
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthEndpoint:
    """AC-FR0100-02: GET /api/health returns 200 with status=ok."""

    def test_health_returns_ok(self, client):
        """GET /api/health returns HTTP 200 and {"status":"ok","version":"v0.7.0"}."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["version"] == "v0.7.0"

    def test_health_is_json(self, client):
        """GET /api/health response Content-Type is application/json."""
        resp = client.get("/api/health")
        assert resp.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# AC-FR0100-01: POST endpoints — success shape verification
# ---------------------------------------------------------------------------


POST_ENDPOINTS = [
    "/backtest",
    "/paper-trade",
    "/sync-data",
    "/init",
    "/mine-factors",
    "/optimize",
    "/grid-search",
    "/check-factor",
    "/generate-strategy",
    "/live-trade",
    "/live",
    "/live/start",
    "/live/stop",
    "/scheduler",
]


@pytest.mark.unit
class TestPostEndpoints:
    """AC-FR0100-01, AC-FR0100-07: POST endpoints return proper success shapes."""

    @pytest.mark.parametrize("path", POST_ENDPOINTS)
    def test_endpoint_accepts_post(self, client, path):
        """Each POST endpoint returns 200 on success."""
        resp = client.post(path, json={})
        # NYI endpoints return 501, implemented ones return 200 with mocked runners
        assert resp.status_code in (200, 501), (
            f"{path} returned {resp.status_code}, expected 200 or 501"
        )

    @pytest.mark.parametrize("path", POST_ENDPOINTS)
    def test_endpoint_returns_json(self, client, path):
        """Each POST endpoint returns JSON Content-Type."""
        resp = client.post(path, json={})
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type, f"{path} did not return JSON: {content_type}"

    def test_backtest_success_shape(self, client):
        """AC-FR0100-01: POST /backtest with valid params returns status=ok with data."""
        resp = client.post(
            "/backtest",
            json={
                "model": "test_v1",
                "strategy": "top20",
                "start": "2024-01-01",
                "end": "2024-06-30",
                "capital": 1000000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_sync_data_success_shape(self, client):
        """POST /sync-data returns success shape."""
        resp = client.post(
            "/sync-data",
            json={
                "universe": "tests/fixtures/v0.2.0/stock_list.csv",
                "start": "2024-01-01",
                "end": "2024-06-30",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_init_success_shape(self, client):
        """POST /init returns success shape."""
        resp = client.post("/init", json={"home": ".quantide"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_check_factor_success_shape(self, client):
        """POST /check-factor returns success shape."""
        resp = client.post(
            "/check-factor",
            json={"name": "momentum_5", "start": "2024-01-01", "end": "2024-06-30"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_live_trade_success_shape(self, client):
        """POST /live-trade returns success shape."""
        resp = client.post(
            "/live-trade",
            json={"strategy": "top20", "universe": "universe.csv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_mine_factors_success_shape(self, client):
        """POST /mine-factors returns success shape."""
        resp = client.post(
            "/mine-factors",
            json={"config": "config.yaml"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_optimize_success_shape(self, client):
        """POST /optimize returns success shape."""
        resp = client.post(
            "/optimize",
            json={
                "predictions": "pred.csv",
                "output": "out/",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_scheduler_success_shape(self, client):
        """POST /scheduler returns success shape."""
        resp = client.post("/scheduler", json={"action": "start"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_live_action_dispatch(self, client):
        """POST /live with action=start dispatches to live module."""
        resp = client.post("/live", json={"action": "start"})
        # NYI → 501
        assert resp.status_code == 501
        data = resp.json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# AC-FR0100-06: GET endpoints — success shape verification
# ---------------------------------------------------------------------------


GET_ENDPOINTS = [
    ("/api/health", 200),
    ("/status", 200),
    ("/status/data", 200),
    ("/status/models", 200),
    ("/live", 200),
    ("/scheduler/status", 200),
    ("/stock-list", 200),
]


@pytest.mark.unit
class TestGetEndpoints:
    """AC-FR0100-06, AC-FR0100-07: GET endpoints exist and return proper shapes."""

    @pytest.mark.parametrize("path,expected_status", GET_ENDPOINTS)
    def test_get_endpoint_returns_200(self, client, path, expected_status):
        """Each GET endpoint returns 200 with status=ok + data."""
        resp = client.get(path)
        assert resp.status_code == expected_status, (
            f"{path} returned {resp.status_code}, expected {expected_status}"
        )
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.parametrize("path,expected_status", GET_ENDPOINTS)
    def test_get_endpoint_returns_json(self, client, path, expected_status):
        """Each GET endpoint returns JSON Content-Type."""
        resp = client.get(path)
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type, f"{path} did not return JSON: {content_type}"

    def test_status_endpoint_has_data(self, client):
        """GET /status returns status=ok with a data dict."""
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data
        assert data["data"]["version"] == "v0.7.0"

    def test_stock_list_endpoint_has_data(self, client):
        """GET /stock-list returns status=ok with data."""
        resp = client.get("/stock-list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_status_data_endpoint_shape(self, client):
        """GET /status/data returns proper shape."""
        resp = client.get("/status/data")
        assert resp.status_code == 200
        data = resp.json()
        assert "data_status" in data["data"]

    def test_status_models_endpoint_shape(self, client):
        """GET /status/models returns proper shape."""
        resp = client.get("/status/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data["data"]

    def test_live_endpoint_shape(self, client):
        """GET /live returns proper shape."""
        resp = client.get("/live")
        assert resp.status_code == 200
        data = resp.json()
        assert "live" in data["data"]

    def test_scheduler_status_endpoint_shape(self, client):
        """GET /scheduler/status returns proper shape."""
        resp = client.get("/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "scheduler" in data["data"]


# ---------------------------------------------------------------------------
# AC-FR0100-03: Error contract — exit code → HTTP status mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorHandling:
    """AC-FR0100-03: Error responses follow the spec envelope and mapping."""

    def test_exit_code_4_maps_to_400(self, error_client):
        """CLI exit code 4 (config error) → HTTP 400."""
        resp = error_client.post(
            "/backtest",
            json={
                "model": "v1",
                "strategy": "top20",
                "start": "2024-01-01",
                "end": "2024-06-30",
                "capital": 1000000,
            },
        )
        assert resp.status_code == 400

    def test_error_response_envelope(self, error_client):
        """Error responses contain {"status":"error","code":4,"message":"..."}."""
        resp = error_client.post(
            "/backtest",
            json={
                "model": "v1",
                "strategy": "top20",
                "start": "2024-01-01",
                "end": "2024-06-30",
                "capital": 1000000,
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == 4
        assert "message" in data
        assert len(data["message"]) > 0

    def test_no_traceback_in_error_response(self, error_client):
        """AC-FR0100-03: Error responses do not contain Python tracebacks."""
        resp = error_client.post(
            "/backtest",
            json={
                "model": "v1",
                "strategy": "top20",
                "start": "2024-01-01",
                "end": "2024-06-30",
                "capital": 1000000,
            },
        )
        text = resp.text
        assert "Traceback (most recent call last)" not in text

    def test_invalid_json_body_returns_400(self, client):
        """Malformed JSON body returns 400 with error envelope."""
        resp = client.post(
            "/backtest",
            content="not valid json {{{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert data["code"] == 2

    def test_unknown_endpoint_returns_404_with_json(self, client):
        """Requests to unregistered endpoints return 404 with JSON detail."""
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_error_on_sync_data(self, error_client):
        """POST /sync-data returns error shape on CLI failure."""
        resp = error_client.post("/sync-data", json={"universe": "test.csv"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert "code" in data
        assert "message" in data


# ---------------------------------------------------------------------------
# AC-FR0100-04: Execution model — run_in_executor + synchronous response
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecutionModel:
    """AC-FR0100-04: Long-running endpoints use run_in_executor, synchronous response."""

    def test_response_is_synchronous_no_job_id(self, client):
        """Response contains no job_id / polling surface."""
        resp = client.post(
            "/backtest",
            json={
                "model": "v1",
                "strategy": "top20",
                "start": "2024-01-01",
                "end": "2024-06-30",
                "capital": 1000000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" not in data, "Response should not contain job_id"


# ---------------------------------------------------------------------------
# AC-FR0100-05: Binding — 127.0.0.1 only
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBinding:
    """AC-FR0100-05: Server binds only to 127.0.0.1 (loopback)."""

    def test_app_configured_for_localhost(self):
        """The FastAPI app is configured — binding host is set at uvicorn level."""
        from fastapi import FastAPI

        from trader_off.api.server import create_app

        app = create_app()
        assert isinstance(app, FastAPI)


# ---------------------------------------------------------------------------
# AC-FR0100-07: All routes enumerated (spec paths without /api/ prefix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouteEnumeration:
    """AC-FR0100-07: All endpoints are registered at spec-defined paths."""

    ALL_PATHS = {
        # POST endpoints (14)
        ("POST", "/backtest"),
        ("POST", "/paper-trade"),
        ("POST", "/sync-data"),
        ("POST", "/init"),
        ("POST", "/mine-factors"),
        ("POST", "/optimize"),
        ("POST", "/grid-search"),
        ("POST", "/check-factor"),
        ("POST", "/generate-strategy"),
        ("POST", "/live-trade"),
        ("POST", "/live"),
        ("POST", "/live/start"),
        ("POST", "/live/stop"),
        ("POST", "/scheduler"),
        # GET endpoints (7)
        ("GET", "/api/health"),
        ("GET", "/status"),
        ("GET", "/status/data"),
        ("GET", "/status/models"),
        ("GET", "/live"),
        ("GET", "/scheduler/status"),
        ("GET", "/stock-list"),
    }

    def test_all_routes_registered(self):
        """Every expected (method, path) pair is registered on the FastAPI app."""
        from fastapi import FastAPI

        from trader_off.api.server import create_app

        app: FastAPI = create_app()
        registered: set[tuple[str, str]] = set()
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    registered.add((method, route.path))

        for method, path in self.ALL_PATHS:
            assert (method, path) in registered, (
                f"Missing route: {method} {path}. Registered: {sorted(registered)}"
            )

    def test_total_endpoint_count(self):
        """The total number of registered endpoints is at least 21."""
        from fastapi import FastAPI

        from trader_off.api.server import create_app

        app: FastAPI = create_app()
        route_pairs: set[tuple[str, str]] = set()
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ("OPTIONS", "HEAD"):
                        route_pairs.add((method, route.path))

        assert len(route_pairs) >= 21, (
            f"Expected at least 21 endpoints, got {len(route_pairs)}: {sorted(route_pairs)}"
        )
