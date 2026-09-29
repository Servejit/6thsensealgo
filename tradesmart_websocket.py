import json
import threading
import time
from typing import Callable, Optional

try:
    import websocket
except ImportError:
    websocket = None


class TradesmartWebSocket:
    """TradeSmart V2 streaming client for touchline, depth, order and position feeds."""

    URL = "wss://v2api.tradesmartonline.in/NorenWSAPI/"

    def __init__(
        self,
        client_id: str,
        access_token: str,
        on_message: Optional[Callable[[dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        reconnect_seconds: float = 3.0,
    ):
        if websocket is None:
            raise RuntimeError("websocket-client is required for TradeSmart streaming.")
        self.client_id = client_id
        self.access_token = access_token
        self.on_message = on_message
        self.on_error = on_error
        self.on_open = on_open
        self.on_close = on_close
        self.reconnect_seconds = float(reconnect_seconds)
        self._ws = None
        self._thread = None
        self._stop = threading.Event()
        self._subscriptions = []
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def subscribe_touchline(self, keys):
        self._subscriptions.append({"t": "t", "k": "#".join(keys)})

    def subscribe_depth(self, keys):
        self._subscriptions.append({"t": "d", "k": "#".join(keys)})

    def subscribe_orders(self):
        self._subscriptions.append({"t": "o", "actid": self.client_id})

    def subscribe_positions(self):
        self._subscriptions.append({"t": "p", "uid": self.client_id})

    def _send_subscriptions(self):
        for payload in self._subscriptions:
            self._ws.send(json.dumps(payload))

    def _on_open(self, ws):
        self._connected = True
        ws.send(json.dumps({
            "t": "a",
            "uid": self.client_id,
            "actid": self.client_id,
            "source": "API",
            "accesstoken": self.access_token,
        }))
        self._send_subscriptions()
        if self.on_open:
            self.on_open()

    def _on_message(self, ws, raw):
        try:
            data = json.loads(raw)
        except Exception as exc:
            if self.on_error:
                self.on_error(exc)
            return
        if data.get("t") != "h" and self.on_message:
            self.on_message(data)

    def _on_error(self, ws, error):
        if self.on_error:
            self.on_error(error)

    def _on_close(self, ws, code, message):
        self._connected = False
        if self.on_close:
            self.on_close()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                )
            except Exception as exc:
                if self.on_error:
                    self.on_error(exc)
            finally:
                self._connected = False
                self._ws = None
            if not self._stop.is_set():
                self._stop.wait(self.reconnect_seconds)

    def start(self, background=True):
        self._stop.clear()
        if background:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            self._run()

    def stop(self):
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._connected = False
