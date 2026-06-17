"""Centrale configuratie.

Laadt instellingen uit de omgeving (.env) met veilige defaults. Eén
``Config``-object wordt door alle modules gedeeld. Geen enkele waarde is strikt
verplicht: zonder OPENAI_API_KEY valt de tool terug op lokale analyse, zonder
DATABASE_URL gebruikt hij SQLite, en zonder Bright Data-velden gaan verzoeken
rechtstreeks naar Reddit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optioneel bij import
    load_dotenv = None  # type: ignore


# Projectwortel = map die deze src/ bevat.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXPORTS_DIR = PROJECT_ROOT / "exports"
LOGS_DIR = PROJECT_ROOT / "logs"


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Optional[str], default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: Optional[str], default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    """Volledige tool-configuratie."""

    # LLM
    llm_provider: str = "anthropic"  # anthropic | openai
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Database
    database_url: Optional[str] = None  # None => SQLite in data/

    # Scrape-limieten
    max_posts_per_query: int = 500
    max_comments_per_post: int = 500
    search_time_filter: str = "all"  # day|week|month|year|all
    search_sort: str = "relevance"  # relevance|hot|top|new|comments

    # Rate limiting
    requests_per_minute: int = 30
    min_delay_seconds: float = 1.0
    max_delay_seconds: float = 5.0
    max_retries: int = 5
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 60.0
    dry_run: bool = False

    # Databron: 'api' (officiële Reddit API), 'direct' (geen proxy), 'proxy' (Bright Data)
    data_source: str = "api"
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None

    # Bright Data proxy
    brightdata_proxy_url: Optional[str] = None
    brightdata_host: str = "brd.superproxy.io"
    brightdata_port: int = 33335
    brightdata_username: Optional[str] = None
    brightdata_password: Optional[str] = None
    brightdata_ssl_verify: bool = True
    brightdata_ca_bundle: Optional[str] = None

    # Netwerk
    user_agent: str = "reddit-research-tool/2.0 (+research)"
    request_timeout_seconds: float = 30.0
    reddit_base_url: str = "https://www.reddit.com"

    # Paden
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    exports_dir: Path = field(default_factory=lambda: EXPORTS_DIR)
    logs_dir: Path = field(default_factory=lambda: LOGS_DIR)

    # ------------------------------------------------------------------ helpers
    @property
    def sqlite_path(self) -> Path:
        """Pad naar de SQLite-database (gebruikt als database_url leeg is)."""
        return self.data_dir / "reddit_research.db"

    @property
    def uses_postgres(self) -> bool:
        return bool(self.database_url) and self.database_url.lower().startswith(
            ("postgres://", "postgresql://")
        )

    @property
    def llm_enabled(self) -> bool:
        """True als de gekozen provider een API-key heeft."""
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.anthropic_api_key)

    @property
    def active_llm_label(self) -> str:
        if not self.llm_enabled:
            return "lokaal (geen key)"
        if self.llm_provider == "openai":
            return f"OpenAI {self.openai_model}"
        return f"Claude {self.anthropic_model}"

    def resolved_proxy_url(self) -> Optional[str]:
        """Bouw de uiteindelijke Bright Data proxy-URL op.

        Geeft voorrang aan een volledige BRIGHTDATA_PROXY_URL; valt anders terug
        op losse host/port/username/password. Retourneert None als er geen proxy
        is geconfigureerd.
        """
        if self.brightdata_proxy_url:
            return self.brightdata_proxy_url
        if self.brightdata_username and self.brightdata_password:
            return (
                f"http://{self.brightdata_username}:{self.brightdata_password}"
                f"@{self.brightdata_host}:{self.brightdata_port}"
            )
        return None

    def proxies(self) -> Optional[Dict[str, str]]:
        """requests-compatibele proxies-dict, of None."""
        url = self.resolved_proxy_url()
        if not url:
            return None
        return {"http": url, "https": url}

    @property
    def proxy_enabled(self) -> bool:
        return self.resolved_proxy_url() is not None

    @property
    def reddit_api_enabled(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def is_api_mode(self) -> bool:
        """True als we via de officiële Reddit API werken."""
        return self.data_source == "api" and self.reddit_api_enabled

    @property
    def data_source_label(self) -> str:
        if self.data_source == "rss":
            return "Reddit RSS-feeds (geen login nodig)"
        if self.is_api_mode:
            return "Officiële Reddit API"
        if self.data_source == "proxy" and self.proxy_enabled:
            return "Bright Data proxy"
        if self.data_source == "api" and not self.reddit_api_enabled:
            return "direct (API-keys ontbreken)"
        return "direct (geen proxy)"

    def ssl_verify(self):
        """Waarde voor ``requests`` ``verify``: pad naar CA-bundel, of bool."""
        if self.brightdata_ca_bundle:
            return self.brightdata_ca_bundle
        return self.brightdata_ssl_verify

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.exports_dir, self.logs_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


def load_config(env_file: Optional[str] = None) -> Config:
    """Lees configuratie uit .env / omgeving en geef een ``Config`` terug."""
    if load_dotenv is not None:
        if env_file:
            load_dotenv(env_file)
        else:
            # Zoek .env in projectwortel.
            default_env = PROJECT_ROOT / ".env"
            load_dotenv(default_env if default_env.exists() else None)

    cfg = Config(
        llm_provider=(os.getenv("LLM_PROVIDER", "anthropic") or "anthropic").strip().lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        database_url=os.getenv("DATABASE_URL") or None,
        data_source=(os.getenv("DATA_SOURCE", "api") or "api").strip().lower(),
        reddit_client_id=os.getenv("REDDIT_CLIENT_ID") or None,
        reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET") or None,
        max_posts_per_query=_as_int(os.getenv("MAX_POSTS_PER_QUERY"), 500),
        max_comments_per_post=_as_int(os.getenv("MAX_COMMENTS_PER_POST"), 500),
        search_time_filter=os.getenv("SEARCH_TIME_FILTER", "all"),
        search_sort=os.getenv("SEARCH_SORT", "relevance"),
        requests_per_minute=_as_int(os.getenv("REQUESTS_PER_MINUTE"), 30),
        min_delay_seconds=_as_float(os.getenv("MIN_DELAY_SECONDS"), 1.0),
        max_delay_seconds=_as_float(os.getenv("MAX_DELAY_SECONDS"), 5.0),
        max_retries=_as_int(os.getenv("MAX_RETRIES"), 5),
        backoff_base_seconds=_as_float(os.getenv("BACKOFF_BASE_SECONDS"), 2.0),
        backoff_max_seconds=_as_float(os.getenv("BACKOFF_MAX_SECONDS"), 60.0),
        dry_run=_as_bool(os.getenv("DRY_RUN"), False),
        brightdata_proxy_url=os.getenv("BRIGHTDATA_PROXY_URL") or None,
        brightdata_host=os.getenv("BRIGHTDATA_HOST", "brd.superproxy.io"),
        brightdata_port=_as_int(os.getenv("BRIGHTDATA_PORT"), 33335),
        brightdata_username=os.getenv("BRIGHTDATA_USERNAME") or None,
        brightdata_password=os.getenv("BRIGHTDATA_PASSWORD") or None,
        brightdata_ssl_verify=_as_bool(os.getenv("BRIGHTDATA_SSL_VERIFY"), True),
        brightdata_ca_bundle=os.getenv("BRIGHTDATA_CA_BUNDLE") or None,
        user_agent=os.getenv(
            "USER_AGENT", "reddit-research-tool/2.0 (+research)"
        ),
        request_timeout_seconds=_as_float(os.getenv("REQUEST_TIMEOUT_SECONDS"), 30.0),
        reddit_base_url=os.getenv("REDDIT_BASE_URL", "https://www.reddit.com").rstrip("/"),
    )
    cfg.ensure_dirs()
    return cfg
