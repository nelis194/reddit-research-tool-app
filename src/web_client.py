"""HTTP-client met nette scraping: rate limiting, retries/backoff en proxy.

Alle netwerkverkeer loopt via deze laag, zodat rate limiting, exponentiële
backoff en de optionele Bright Data proxy op één plek geregeld zijn.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

import requests

from .config import Config
from .utils import get_logger

logger = get_logger()


class RateLimiter:
    """Eenvoudige rolling-window limiter + jitter-delay tussen requests.

    Combineert twee mechanismen:
    * een hard maximum aantal requests per minuut (rolling window);
    * een willekeurige delay tussen ``min_delay`` en ``max_delay`` om niet als
      bot op te vallen.
    """

    def __init__(self, requests_per_minute: int, min_delay: float, max_delay: float):
        self.requests_per_minute = max(1, requests_per_minute)
        self.min_delay = max(0.0, min_delay)
        self.max_delay = max(self.min_delay, max_delay)
        self._timestamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            window_start = now - 60.0
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.requests_per_minute:
                sleep_for = 60.0 - (now - self._timestamps[0]) + 0.05
                if sleep_for > 0:
                    logger.debug("Rate limit bereikt; wacht %.2fs", sleep_for)
                    time.sleep(sleep_for)

            # Jitter-delay.
            delay = random.uniform(self.min_delay, self.max_delay)
            if delay > 0:
                time.sleep(delay)

            self._timestamps.append(time.monotonic())


class WebClient:
    """requests-gebaseerde client met retries, backoff en proxy-ondersteuning."""

    def __init__(self, config: Config):
        self.config = config
        self.limiter = RateLimiter(
            config.requests_per_minute,
            config.min_delay_seconds,
            config.max_delay_seconds,
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        # Proxy alleen gebruiken in expliciete proxy-modus.
        self._proxies = config.proxies() if config.data_source == "proxy" else None
        self._verify = config.ssl_verify()
        if self._proxies:
            logger.info("Bright Data proxy actief voor uitgaande verzoeken.")
        if config.dry_run:
            logger.warning("DRY_RUN actief: er worden geen echte verzoeken gedaan.")

    def set_bearer_token(self, token: str) -> None:
        """Zet de OAuth-bearer-header (voor de officiële Reddit API)."""
        self.session.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------ public
    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Haal JSON op. Geeft de geparste payload terug, of None bij falen."""
        resp = self._request(url, params=params, expect="json")
        if resp is None:
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning("Antwoord van %s was geen geldige JSON.", url)
            return None

    def get_text(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Haal ruwe tekst/HTML op (voor de BeautifulSoup-fallback)."""
        resp = self._request(url, params=params, expect="text")
        return resp.text if resp is not None else None

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "WebClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----------------------------------------------------------------- internal
    def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]],
        expect: str,
    ) -> Optional[requests.Response]:
        if self.config.dry_run:
            logger.info("[DRY_RUN] GET %s params=%s", url, params)
            return None

        attempt = 0
        while attempt <= self.config.max_retries:
            self.limiter.wait()
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    timeout=self.config.request_timeout_seconds,
                    proxies=self._proxies,
                    verify=self._verify,
                )
            except requests.RequestException as exc:
                logger.warning("Netwerkfout (poging %d) op %s: %s", attempt + 1, url, exc)
                if not self._sleep_backoff(attempt):
                    return None
                attempt += 1
                continue

            if resp.status_code == 200:
                return resp

            # Retry op rate-limit / serverfouten.
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = self._retry_after(resp)
                logger.warning(
                    "HTTP %d op %s (poging %d). Retry...",
                    resp.status_code,
                    url,
                    attempt + 1,
                )
                self._sleep_backoff(attempt, override=retry_after)
                attempt += 1
                continue

            logger.error("HTTP %d op %s; geen retry.", resp.status_code, url)
            return None

        logger.error("Maximaal aantal pogingen bereikt voor %s.", url)
        return None

    def _sleep_backoff(self, attempt: int, override: Optional[float] = None) -> bool:
        """Slaap volgens exponentiële backoff. Geeft False bij laatste poging."""
        if attempt >= self.config.max_retries:
            return False
        if override is not None:
            delay = override
        else:
            delay = min(
                self.config.backoff_base_seconds * (2 ** attempt),
                self.config.backoff_max_seconds,
            )
            delay += random.uniform(0, 1.0)  # jitter
        logger.debug("Backoff %.2fs (poging %d)", delay, attempt + 1)
        time.sleep(delay)
        return True

    @staticmethod
    def _retry_after(resp: requests.Response) -> Optional[float]:
        value = resp.headers.get("Retry-After")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
