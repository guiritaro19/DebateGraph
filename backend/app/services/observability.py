import logging
from typing import Protocol


class Observer(Protocol):
    def node(self, event: dict) -> None: ...


class LoggingObserver:
    def node(self, event):
        logging.getLogger("debategraph.nodes").info("node %s", event)
