"""QMT Gateway Broker (FR-0100).

HTTP client wrapper for the qmt-gateway service.
Provides live trading access via REST API.

NFR-0100: httpx is imported at function scope (lazy import).  # noqa: I001
"""

from urllib.parse import urlparse


class QmtGatewayBroker:
    """Broker that wraps qmt-gateway HTTP API for live trading.

    qmt-gateway is the recommended path for live trading (QMTBroker was
    removed from quantide main). It exposes REST endpoints for account
    queries, order placement, and cancellation.

    Endpoints:
        GET  /asset
        GET  /positions
        GET  /orders?status=all
        GET  /trades
        POST /buy_stock?symbol=&price=&shares=&qtoid=
        POST /sell_stock?symbol=&price=&shares=&qtoid=
        POST /cancel_order?qtoid=
        POST /update_principal?principal=
        GET  /connection_status
        POST /restart_qmt?password=
        GET  /search_stocks?q=
        GET  /stock_info?symbol=
        GET  /all_stocks
    """

    def __init__(self, base_url: str = "http://localhost:5800", api_key: str | None = None):
        """Initialize the gateway broker.

        Args:
            base_url: qmt-gateway service URL. Defaults to localhost:5800.
            api_key: Optional API key for authentication.

        Raises:
            ValueError: If base_url format is invalid.
        """
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid base_url: {base_url}")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._username: str | None = None
        self._password: str | None = None

    def login(self, username: str, password: str) -> None:
        """Authenticate session with gateway (if gateway requires).

        Args:
            username: Login username.
            password: Login password.
        """
        self._username = username
        self._password = password

    def _get_client(self):
        """Create an httpx Client instance (lazy import per NFR-0100).

        Returns:
            httpx.Client configured with base headers.
        """
        import httpx  # noqa: I001 — lazy import per NFR-0100

        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return httpx.Client(base_url=self.base_url, headers=headers)

    def get_account(self) -> dict:
        """Get account info via GET /asset.

        Returns:
            Parsed JSON dict with account information.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/asset")

    def get_positions(self) -> list[dict]:
        """Get current positions via GET /positions.

        Returns:
            List of position dicts.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/positions")

    def get_orders(self, status: str = "all") -> list[dict]:
        """Get orders via GET /orders.

        Args:
            status: Order status filter. Defaults to "all".

        Returns:
            List of order dicts.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/orders", params={"status": status})

    def get_trades(self) -> list[dict]:
        """Get trade records via GET /trades.

        Returns:
            List of trade dicts.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/trades")

    def buy(self, symbol: str, price: float, shares: int, qtoid: str = "") -> dict:
        """Place a buy order via POST /buy_stock.

        Args:
            symbol: Stock symbol (e.g., "000001.SZ").
            price: Order price.
            shares: Number of shares.
            qtoid: Optional quantide order ID.

        Returns:
            Parsed JSON dict with order result.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post(
            "/buy_stock",
            params={"symbol": symbol, "price": price, "shares": shares, "qtoid": qtoid},
        )

    def sell(self, symbol: str, price: float, shares: int, qtoid: str = "") -> dict:
        """Place a sell order via POST /sell_stock.

        Args:
            symbol: Stock symbol (e.g., "600000.SH").
            price: Order price.
            shares: Number of shares.
            qtoid: Optional quantide order ID.

        Returns:
            Parsed JSON dict with order result.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post(
            "/sell_stock",
            params={"symbol": symbol, "price": price, "shares": shares, "qtoid": qtoid},
        )

    def cancel_order(self, qtoid: str) -> dict:
        """Cancel an order via POST /cancel_order.

        Args:
            qtoid: Quantide order ID to cancel.

        Returns:
            Parsed JSON dict with cancellation result.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/cancel_order", params={"qtoid": qtoid})

    def set_principal(self, amount: float) -> dict:
        """Set trading principal via POST /update_principal.

        Args:
            amount: Principal amount in CNY.

        Returns:
            Parsed JSON dict with update result.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/update_principal", params={"principal": amount})

    # ------------------------------------------------------------------
    # Connection management (FR-0100 P0)
    # ------------------------------------------------------------------

    def get_connection_status(self) -> dict:
        """Check if QMT gateway is connected via GET /connection_status.

        Returns:
            Parsed JSON dict with connection state (e.g., connected, qmt_version).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/connection_status")

    def restart_qmt(self, password: str) -> dict:
        """Restart QMT application via POST /restart_qmt.

        Args:
            password: QMT application password.

        Returns:
            Parsed JSON dict with restart status.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/restart_qmt", params={"password": password})

    # ------------------------------------------------------------------
    # Stock search (FR-0100 P0)
    # ------------------------------------------------------------------

    def search_stocks(self, q: str) -> list[dict]:
        """Search stocks by keyword via GET /search_stocks.

        Args:
            q: Search keyword (e.g., stock name or symbol fragment).

        Returns:
            List of matching stock dicts with symbol/name info.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/search_stocks", params={"q": q})

    def get_stock_info(self, symbol: str) -> dict:
        """Get detailed stock info via GET /stock_info.

        Args:
            symbol: Full stock symbol (e.g., "000001.SZ").

        Returns:
            Parsed JSON dict with stock details (name, sector, etc.).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/stock_info", params={"symbol": symbol})

    def get_all_stocks(self) -> list[dict]:
        """Get all available stocks via GET /all_stocks.

        Returns:
            List of stock dicts with symbol/name info.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/all_stocks")

    # ------------------------------------------------------------------
    # Minutes download (FR-0100 P1)
    # ------------------------------------------------------------------

    def get_minutes_job(self, job_id: str) -> dict:
        """Query minutes download progress via GET /minutes_job/{job_id}.

        Args:
            job_id: The download job ID returned by download_minutes.

        Returns:
            Parsed JSON dict with progress info (job_id, progress, status).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get(f"/minutes_job/{job_id}")

    def download_minutes(self, dates: list[str]) -> dict:
        """Start a minutes download job via POST /download_minutes.

        Args:
            dates: List of date strings (e.g., ["2024-01-02", "2024-01-03"]).

        Returns:
            Parsed JSON dict containing job_id and initial status.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/download_minutes", params={"dates": ",".join(dates)})

    # ------------------------------------------------------------------
    # Quote & auction status (FR-0100 P1)
    # ------------------------------------------------------------------

    def get_quote_status(self) -> dict:
        """Check WebSocket quote subscription status via GET /quote_status.

        Returns:
            Parsed JSON dict with subscription state (e.g., subscribed, symbols).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/quote_status")

    def get_auction_status(self) -> dict:
        """Check auction session status via GET /auction_status.

        Returns:
            Parsed JSON dict with auction phase info (e.g., is_auction_time, phase).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/auction_status")

    # ------------------------------------------------------------------
    # System management (FR-0100 P2)
    # ------------------------------------------------------------------

    def get_version(self) -> dict:
        """Get gateway version info via GET /api/system/version.

        Returns:
            Parsed JSON dict with version and build info.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/api/system/version")

    def check_version(self) -> dict:
        """Check for available updates via POST /api/system/version/check.

        Returns:
            Parsed JSON dict with up-to-date status and latest version.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/api/system/version/check")

    def start_update(self) -> dict:
        """Trigger gateway update via POST /api/system/update.

        Returns:
            Parsed JSON dict with update initiation status.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/api/system/update")

    def get_update_status(self, task_id: str) -> dict:
        """Query update job progress via GET /api/system/update/status/{task_id}.

        Args:
            task_id: The update task ID returned by start_update.

        Returns:
            Parsed JSON dict with progress info (task_id, progress, status).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get(f"/api/system/update/status/{task_id}")

    def do_rollback(self) -> dict:
        """Roll back to previous version via POST /api/system/rollback.

        Returns:
            Parsed JSON dict with rollback status.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/api/system/rollback")

    def get_autostart(self) -> dict:
        """Get autostart configuration via GET /api/system/autostart.

        Returns:
            Parsed JSON dict with autostart enabled/disabled state.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/api/system/autostart")

    def set_autostart(self, enabled: bool) -> dict:
        """Set autostart configuration via POST /api/system/autostart.

        Args:
            enabled: True to enable autostart, False to disable.

        Returns:
            Parsed JSON dict with new autostart state.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post(
            "/api/system/autostart",
            form_data={"enabled": "true" if enabled else "false"},
        )

    def get_port(self) -> dict:
        """Get gateway service port via GET /api/system/port.

        Returns:
            Parsed JSON dict with port number.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/api/system/port")

    def get_firewall(self) -> dict:
        """Get firewall rules via GET /api/system/firewall.

        Returns:
            Parsed JSON dict with current firewall rule list.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/api/system/firewall")

    def update_firewall(self, rules: list[dict]) -> dict:
        """Update firewall rules via POST /api/system/firewall.

        Args:
            rules: List of firewall rule dicts.

        Returns:
            Parsed JSON dict with update confirmation.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        import json as _json

        return self._post("/api/system/firewall", form_data={"rules": _json.dumps(rules)})

    # ------------------------------------------------------------------
    # API key management (FR-0100 P2)
    # ------------------------------------------------------------------

    def create_api_key(self, name: str) -> dict:
        """Create a new API key via POST /api/api-keys.

        Args:
            name: Display name for the API key.

        Returns:
            Parsed JSON dict with key details (id, name, key).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._post("/api/api-keys", form_data={"name": name})

    def list_api_keys(self) -> list[dict]:
        """List all API keys via GET /api/api-keys.

        Returns:
            List of API key dicts (id, name, created_at, etc.).

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._get("/api/api-keys")

    def revoke_api_key(self, key_id: str) -> dict:
        """Revoke an API key via DELETE /api/api-keys/{key_id}.

        Args:
            key_id: The API key ID to revoke.

        Returns:
            Parsed JSON dict with revocation confirmation.

        Raises:
            RuntimeError: If the HTTP request fails.
        """
        return self._request("DELETE", f"/api/api-keys/{key_id}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None):
        """Perform a GET request and return parsed JSON.

        Args:
            path: URL path (e.g., "/asset").
            params: Optional query parameters.

        Returns:
            Parsed JSON response (dict or list[dict]).

        Raises:
            RuntimeError: On non-200 status or network failure.
        """
        return self._request("GET", path, params=params)

    def _post(
        self,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        form_data: dict | None = None,
    ):
        """Perform a POST request and return parsed JSON.

        Args:
            path: URL path (e.g., "/buy_stock").
            params: Optional query parameters.
            json_body: Optional JSON body payload.
            form_data: Optional form-encoded body payload.

        Returns:
            Parsed JSON response (dict or list[dict]).

        Raises:
            RuntimeError: On non-200 status or network failure.
        """
        return self._request("POST", path, params=params, json_body=json_body, form_data=form_data)

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        form_data: dict | None = None,
    ):
        """Execute an HTTP request and return parsed JSON.

        Args:
            method: HTTP method ("GET", "POST", or "DELETE").
            path: URL path.
            params: Optional query parameters.
            json_body: Optional JSON body payload.
            form_data: Optional form-encoded body payload.

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On non-200 status or network failure.
        """
        import httpx  # noqa: I001 — lazy import per NFR-0100

        try:
            with self._get_client() as client:
                kwargs = {"params": params}
                if json_body is not None:
                    kwargs["json"] = json_body
                if form_data is not None:
                    kwargs["data"] = form_data
                response = client.request(method, path, **kwargs)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text.strip()}")
                return response.json()
        except httpx.RequestError as e:
            raise RuntimeError(f"Request failed: {e}") from e
