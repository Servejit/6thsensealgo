from abc import ABC, abstractmethod

class BrokerAdapter(ABC):
    """Interface for a future authenticated broker integration."""
    @abstractmethod
    def submit_market_order(self, symbol, side, quantity):
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id):
        raise NotImplementedError

    @abstractmethod
    def get_positions(self):
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id):
        raise NotImplementedError

class DisabledLiveBroker(BrokerAdapter):
    def submit_market_order(self, symbol, side, quantity):
        raise RuntimeError("Live broker execution is disabled.")

    def get_order_status(self, order_id):
        raise RuntimeError("Live broker execution is disabled.")

    def get_positions(self):
        raise RuntimeError("Live broker execution is disabled.")

    def cancel_order(self, order_id):
        raise RuntimeError("Live broker execution is disabled.")
