from __future__ import annotations

from typing import Protocol

from ..models import Alert


class Notifier(Protocol):
    def send(self, alert: Alert) -> None: ...
