import os
import time
import json
import hashlib
from datetime import datetime
from typing import Optional

import requests

from broker_adapter import BrokerAdapter
from order_engine import Order, OrderState
from state_store import save_order


class TradesmartBroker(BrokerAdapter):
    """TradeSmart API v2 live broker adapter.

    Credentials are read from environment variables:
      TRADESMART_CLIENT_ID
      TRADESMART_ACCESS_TOKEN
      TRADESMART_EXCHANGE (default NSE)
      TRADESMART_PRODUCT (default MIS)
      TRADESMART_ORDER_TYPE (default LMT)
      TRADESMART_RETURN (default DAY)

    The access token must be obtained through TradeSmart's authentication flow.
    No secret is stored in source code.
    """

    BASE_URL = "https://v2api.tradesmartonline.in/NorenWClientAPIv2"

    def __init__(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        exchange: Optional[str] = None,
        product: Optional[str] = None,
        order_type: Optional[str] = None,
        retention: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.client_id = client_id or os.getenv("TRADESMART_CLIENT_ID", "")
        self.access_token = access_token or os.getenv("TRADESMART_ACCESS_TOKEN", "")
        self.base_url = (base_url or os.getenv("TRADESMART_BASE_URL", self.BASE_URL)).rstrip("/")
        self.exchange = exchange or os.getenv("TRADESMART_EXCHANGE", "NSE")
        self.product = product or os.getenv("TRADESMART_PRODUCT", "MIS")
        self.order_type = order_type or os.getenv("TRADESMART_ORDER_TYPE", "LMT")
        self.retention = retention or os.getenv("TRADESMART_RET", "DAY")
        self.timeout = float(timeout)
        self.session = requests.Session()

    def _require_auth(self):
        if not self.client_id:
            raise RuntimeError("TRADESMART_CLIENT_ID is not configured.")
        if not self.access_token:
            raise RuntimeError("TRADESMART_ACCESS_TOKEN is not configured.")

    def _post(self, endpoint, payload):
        self._require_auth()
        url = f"{self.base_url}/{endpoint}"
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            data="jData=" + __import__("json").dumps(payload, separators=(",", ":")),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("stat") != "Ok":
            raise RuntimeError(data.get("emsg", "TradeSmart API request failed."))
        return data

    def generate_access_token(self, app_key, secret_key, authorization_code):
        checksum = hashlib.sha256(
            f"{app_key}{secret_key}{authorization_code}".encode()
        ).hexdigest()
        response = self.session.post(
            f"{self.base_url}/GenAcsTok",
            data="jData=" + json.dumps(
                {"code": authorization_code, "checksum": checksum},
                separators=(",", ":"),
            ),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("stat") != "Ok":
            raise RuntimeError(data.get("emsg", "TradeSmart token exchange failed."))
        token = data.get("access_token")
        if not token:
            raise RuntimeError("TradeSmart token exchange returned no access_token.")
        return token

    def user_details(self):
        return self._post("UserDetails", {"uid": self.client_id})

    def submit_market_order(self, symbol, side, quantity, price=0.0, **kwargs):
        self._require_auth()
        exchange = kwargs.get("exchange", self.exchange)
        product = kwargs.get("product", self.product)
        order_type = kwargs.get("order_type", self.order_type).upper()
        retention = kwargs.get("retention", self.retention)

        payload = {
            "uid": self.client_id,
            "actid": self.client_id,
            "exch": exchange,
            "tsym": symbol,
            "qty": str(int(quantity)),
            "prc": str(float(price) if order_type != "MKT" else 0),
            "prd": product,
            "trantype": "B" if side.upper() == "BUY" else "S",
            "prctyp": order_type,
            "ret": retention,
            "ordersource": "API",
        }
        return self._post("PlaceOrder", payload)

    def get_order_status(self, order_id):
        data = self._post(
            "SingleOrdHist",
            {"uid": self.client_id, "norenordno": str(order_id)},
        )
        if isinstance(data, list):
            return data[-1] if data else {}
        return data

    def limits(self):
        return self._post("Limits", {"uid": self.client_id, "actid": self.client_id})

    def search_script(self, searchtext, exchange=None):
        payload = {"uid": self.client_id, "stext": str(searchtext)}
        if exchange:
            payload["exch"] = exchange
        data = self._post("SearchScrip", payload)
        return data.get("values", []) if isinstance(data, dict) else []

    def historical_candles(self, exchange, token, interval=5, lookback_days=5):
        """Fetch TradeSmart TPSeries candles for live strategy warm-up."""
        import time as _time
        end_ts = int(_time.time())
        start_ts = end_ts - int(float(lookback_days) * 86400)
        payload = {
            "uid": self.client_id,
            "exch": str(exchange),
            "token": str(token),
            "st": str(start_ts),
            "et": str(end_ts),
            "intrv": str(int(interval)),
        }
        data = self._post("TPSeries", payload)
        rows = data.get("values", []) if isinstance(data, dict) else []
        if not rows and isinstance(data, list):
            rows = data
        records = []
        for row in rows:
            records.append({
                "timestamp": row.get("time") or row.get("timestamp"),
                "open": row.get("into"),
                "high": row.get("inth"),
                "low": row.get("intl"),
                "close": row.get("intc"),
                "volume": row.get("intv", row.get("v", 0)),
            })
        frame = __import__("pandas").DataFrame(records)
        if frame.empty:
            return frame
        frame["timestamp"] = __import__("pandas").to_datetime(
            frame["timestamp"], errors="coerce", utc=True, dayfirst=True
        )
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = __import__("pandas").to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
        return frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    def get_positions(self):
        return self._post("PositionBook", {"uid": self.client_id})

    def cancel_order(self, order_id):
        return self._post(
            "CancelOrder",
            {"uid": self.client_id, "norenordno": str(order_id)},
        )

    def submit(self, symbol, side, quantity, price, reason="", **kwargs):
        response = self.submit_market_order(
            symbol, side, quantity, price, **kwargs
        )
        order_id = str(response.get("norenordno", ""))
        if not order_id:
            raise RuntimeError("TradeSmart accepted no order number.")

        now = datetime.utcnow().isoformat()
        status = OrderState.SUBMITTED.value
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side.upper(),
            quantity=int(quantity),
            order_type=kwargs.get("order_type", self.order_type).upper(),
            price=float(price),
            status=status,
            created_at=now,
            reason=reason,
        )
        save_order(order)
        return order

    def refresh_order(self, order):
        data = self.get_order_status(order.order_id)
        raw = str(data.get("status", "")).upper()
        mapping = {
            "NEW": OrderState.SUBMITTED.value,
            "PENDING": OrderState.SUBMITTED.value,
            "OPEN": OrderState.OPEN.value,
            "TRIGGER_PENDING": OrderState.OPEN.value,
            "COMPLETE": OrderState.FILLED.value,
            "CANCELED": OrderState.CANCELLED.value,
            "CANCELLED": OrderState.CANCELLED.value,
            "REJECTED": OrderState.REJECTED.value,
        }
        target = mapping.get(raw)
        if target and target != order.status:
            order.transition(target)
        return order

    def broker_orders(self, symbol=None):
        # OrderBook endpoint returns the current broker order book.
        payload = self._post("OrderBook", {"uid": self.client_id})
        return payload if isinstance(payload, list) else [payload]
