from __future__ import annotations

from ..models import Alert


class ConsoleNotifier:
    def send(self, alert: Alert) -> None:
        link = f"\n  {alert.url}" if alert.url else ""
        print(f"[ALERT:{alert.kind}] {alert.title}\n  {alert.message}{link}")
