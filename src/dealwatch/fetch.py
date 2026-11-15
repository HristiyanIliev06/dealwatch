from __future__ import annotations

import logging
import random
import time
from urllib.parse import urlsplit

import requests
from protego import Protego

log = logging.getLogger(__name__)


class FetchError(Exception):
    pass


class Fetcher:
    """HTTP client that checks robots.txt and spaces out requests to the same host."""

    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 3.0,
        timeout: float = 20.0,
        respect_robots: bool = True,
        retries: int = 2,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.retries = retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, Protego | None] = {}
        self._browser = None

    def get(self, url: str, browser: bool = False, check_robots: bool = True) -> str:
        """Fetch a page. `check_robots=False` is only for documented public APIs, whose
        robots.txt targets crawlers (e.g. CheapShark, which invites programmatic use)."""
        host = urlsplit(url).netloc
        if self.respect_robots and check_robots and not self._allowed(url):
            raise FetchError(f"robots.txt disallows {url}")
        if browser:
            self._wait(host)
            return self._browser_session().get(url)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait(host)
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code >= 500:
                    raise FetchError(f"HTTP {response.status_code} from {host}")
                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code} from {url}")
                return response.text
            except requests.RequestException as exc:
                last_error = exc
            except FetchError as exc:
                if "HTTP 4" in str(exc):
                    raise
                last_error = exc
            log.warning("fetch attempt %d failed for %s: %s", attempt + 1, url, last_error)
        raise FetchError(f"giving up on {url}: {last_error}")

    def _browser_session(self):
        if self._browser is None:
            from .browser import BrowserSession

            self._browser = BrowserSession()
        return self._browser

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def _wait(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay_seconds + random.uniform(0, 1) - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            try:
                response = self.session.get(f"{origin}/robots.txt", timeout=self.timeout)
                # No robots.txt means nothing is disallowed.
                self._robots[origin] = Protego.parse(response.text) if response.status_code == 200 else None
            except requests.RequestException:
                self._robots[origin] = None
        rules = self._robots[origin]
        return rules is None or rules.can_fetch(url, self.session.headers["User-Agent"])
