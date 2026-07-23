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

    def _post(self, path: str, params: dict | None = None):
        """Perform a POST request and return parsed JSON.

        Args:
            path: URL path (e.g., "/buy_stock").
            params: Optional query parameters.

        Returns:
            Parsed JSON response (dict or list[dict]).

        Raises:
            RuntimeError: On non-200 status or network failure.
        """
        return self._request("POST", path, params=params)

    def _request(self, method: str, path: str, params: dict | None = None):
        """Execute an HTTP request and return parsed JSON.

        Args:
            method: HTTP method ("GET" or "POST").
            path: URL path.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On non-200 status or network failure.
        """
        import httpx  # noqa: I001 — lazy import per NFR-0100

        try:
            with self._get_client() as client:
                response = client.request(method, path, params=params)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text.strip()}")
                return response.json()
        except httpx.RequestError as e:
            raise RuntimeError(f"Request failed: {e}") from e
