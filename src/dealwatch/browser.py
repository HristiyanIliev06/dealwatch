from __future__ import annotations

import logging

from .fetch import FetchError

log = logging.getLogger(__name__)


class BrowserSession:
    """Fetches fully rendered pages through an installed Chromium-family browser.

    Meant for shops that refuse plain HTTP clients or build the page with JavaScript.
    The browser starts on first use and is reused for the rest of the run.
    """

    def __init__(self, channel: str = "msedge", timeout_ms: int = 30_000) -> None:
        self.channel = channel
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None

    def get(self, url: str) -> str:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeout
        except ImportError as exc:
            raise FetchError("fetch: browser needs the 'playwright' package") from exc

        try:
            page = self._new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                if response is not None and response.status >= 400:
                    raise FetchError(f"HTTP {response.status} from {url} (browser)")
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightTimeout:
                    log.debug("network never went idle for %s; using the page as loaded", url)
                return page.content()
            finally:
                page.close()
        except PlaywrightError as exc:
            raise FetchError(f"browser fetch of {url} failed: {exc}") from exc

    def _new_page(self):
        if self._context is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(channel=self.channel, headless=True)
            self._context = self._browser.new_context(locale="bg-BG")
        return self._context.new_page()

    def close(self) -> None:
        for resource in (self._context, self._browser):
            if resource is not None:
                resource.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = self._browser = self._playwright = None
