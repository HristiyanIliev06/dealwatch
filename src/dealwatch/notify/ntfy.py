from __future__ import annotations

import requests

from ..models import Alert


class NtfyNotifier:
    def __init__(self, topic: str, server: str = "https://ntfy.sh", timeout: float = 15.0) -> None:
        self.topic = topic
        self.server = server.rstrip("/")
        self.timeout = timeout

    def send(self, alert: Alert) -> None:
        # JSON publishing keeps non-ASCII titles intact (HTTP headers would not).
        payload = {
            "topic": self.topic,
            "title": alert.title,
            "message": alert.message,
            "priority": alert.priority,
        }
        if alert.url:
            payload["click"] = alert.url
        response = requests.post(self.server, json=payload, timeout=self.timeout)
        response.raise_for_status()
