from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

from .base import Notifier
from .console import ConsoleNotifier
from .ntfy import NtfyNotifier


class NotifierConfigError(Exception):
    pass


def build_notifiers(
    names: Iterable[str], env: Mapping[str, str] = os.environ
) -> dict[str, Notifier]:
    notifiers: dict[str, Notifier] = {}
    for name in names:
        if name == "console":
            notifiers[name] = ConsoleNotifier()
        elif name == "ntfy":
            topic = env.get("NTFY_TOPIC")
            if not topic:
                raise NotifierConfigError("notifier 'ntfy' needs NTFY_TOPIC in the environment/.env")
            notifiers[name] = NtfyNotifier(topic, env.get("NTFY_SERVER", "https://ntfy.sh"))
        else:
            raise NotifierConfigError(f"unknown notifier {name!r}")
    return notifiers
