"""OAuth voor de officiële Reddit API (application-only / userless).

Met een ``client_id`` + ``client_secret`` (van https://www.reddit.com/prefs/apps)
halen we een read-only bearer-token op via de ``client_credentials`` grant. Geen
gebruikersnaam/wachtwoord nodig; we lezen alleen publieke listings/search.

Het token wordt in-process gecachet tot kort voor het verloopt.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from .config import Config
from .utils import get_logger

logger = get_logger()

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE_URL = "https://oauth.reddit.com"


class RedditTokenError(RuntimeError):
    """Wordt geworpen als het ophalen van een token mislukt."""


class TokenProvider:
    """Haalt en cachet een application-only OAuth-token."""

    def __init__(self, config: Config):
        self.config = config
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        # Hergebruik het token tot 60s voor verloop.
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token

        if not self.config.reddit_api_enabled:
            raise RedditTokenError(
                "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET ontbreken in .env."
            )

        resp = requests.post(
            TOKEN_URL,
            auth=(self.config.reddit_client_id, self.config.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.config.user_agent},
            timeout=self.config.request_timeout_seconds,
        )
        if resp.status_code != 200:
            raise RedditTokenError(
                f"Token ophalen mislukt (HTTP {resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RedditTokenError(f"Geen access_token in antwoord: {data}")
        self._token = token
        self._expires_at = time.monotonic() + float(data.get("expires_in", 3600))
        logger.info("Reddit OAuth-token opgehaald (geldig ~%ss).", data.get("expires_in"))
        return token
