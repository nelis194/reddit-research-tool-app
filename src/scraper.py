"""Reddit-scraper bovenop ``WebClient``.

Gebruikt Reddit's publieke JSON-endpoints (``.json``). Ondersteunt:
* zoeken in heel Reddit en binnen specifieke subreddits;
* meerdere keywords / onderwerpen / concurrenten tegelijk;
* sortering (relevance/hot/top/new/comments) en time-filter (day..all);
* limieten per keyword en per subreddit;
* paginatie via het ``after``-token;
* duplicate detection over posts en comments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set

from .config import Config
from .parser import (
    Comment,
    Post,
    parse_comments,
    parse_html_search,
    parse_post_listing,
)
from .utils import get_logger
from .web_client import WebClient

logger = get_logger()

VALID_SORTS = {"relevance", "hot", "top", "new", "comments"}
VALID_TIME_FILTERS = {"day", "week", "month", "year", "all"}

# Reddit staat maximaal 100 items per listing-pagina toe.
PAGE_SIZE = 100


@dataclass
class ScrapeResult:
    """Verzameld resultaat van een scrape-run."""

    posts: List[Post] = field(default_factory=list)
    comments: List[Comment] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)
    subreddits: List[str] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        return {
            "posts": len(self.posts),
            "comments": len(self.comments),
            "queries": len(self.queries),
        }


# Callback-type voor voortgang: (fase, huidig, totaal, bericht)
ProgressFn = Callable[[str, int, int, str], None]


class RedditScraper:
    """Hoog-niveau scraper die ``ScrapeResult`` oplevert."""

    def __init__(self, config: Config, client: Optional[WebClient] = None):
        self.config = config
        self.client = client or WebClient(config)
        self._owns_client = client is None
        self._token_provider = None
        if config.is_api_mode:
            from .reddit_auth import TokenProvider

            self._token_provider = TokenProvider(config)
            self.client.set_bearer_token(self._token_provider.get_token())
            logger.info("Officiële Reddit API actief (OAuth).")

    def _refresh_token(self) -> None:
        """Vernieuw (indien nodig) het OAuth-token voor de volgende request."""
        if self._token_provider is not None:
            self.client.set_bearer_token(self._token_provider.get_token())

    @property
    def _api(self) -> bool:
        return self.config.is_api_mode

    def _search_url(self, subreddit: Optional[str]) -> str:
        if self._api:
            base = "https://oauth.reddit.com"
            return f"{base}/r/{subreddit}/search" if subreddit else f"{base}/search"
        base = self.config.reddit_base_url
        return f"{base}/r/{subreddit}/search.json" if subreddit else f"{base}/search.json"

    def _comments_url(self, permalink: str) -> str:
        if self._api:
            # permalink is absoluut op www.reddit.com; pak alleen het pad.
            from urllib.parse import urlparse

            path = urlparse(permalink).path.rstrip("/")
            return f"https://oauth.reddit.com{path}"
        return permalink.rstrip("/") + ".json"

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    # ------------------------------------------------------------------ search
    def scrape(
        self,
        keywords: Iterable[str],
        subreddits: Optional[Iterable[str]] = None,
        sort: Optional[str] = None,
        time_filter: Optional[str] = None,
        max_posts_per_query: Optional[int] = None,
        max_comments_per_post: Optional[int] = None,
        fetch_comments: bool = True,
        progress: Optional[ProgressFn] = None,
    ) -> ScrapeResult:
        """Voer een complete scrape uit voor alle keyword/subreddit-combinaties."""
        keywords = [k for k in keywords if k and k.strip()]
        subreddits = [s.strip().lstrip("r/").strip("/") for s in (subreddits or []) if s and s.strip()]
        sort = self._validate(sort or self.config.search_sort, VALID_SORTS, "relevance")
        time_filter = self._validate(
            time_filter or self.config.search_time_filter, VALID_TIME_FILTERS, "all"
        )
        max_posts = max_posts_per_query or self.config.max_posts_per_query
        max_comments = max_comments_per_post or self.config.max_comments_per_post

        result = ScrapeResult(subreddits=list(subreddits))
        seen_posts: Set[str] = set()
        seen_comments: Set[str] = set()

        # Bepaal de werklijst: elke (keyword, subreddit)-combinatie, of keyword
        # over heel Reddit als er geen subreddits zijn opgegeven.
        targets = []
        for kw in keywords:
            if subreddits:
                for sub in subreddits:
                    targets.append((kw, sub))
            else:
                targets.append((kw, None))

        total = len(targets)
        for idx, (kw, sub) in enumerate(targets, start=1):
            label = f"'{kw}'" + (f" in r/{sub}" if sub else " (heel Reddit)")
            if progress:
                progress("search", idx, total, f"Zoeken: {label}")
            logger.info("Zoeken naar %s [sort=%s, t=%s]", label, sort, time_filter)
            result.queries.append(label)

            posts = self._search(kw, sub, sort, time_filter, max_posts)
            new_posts = self._dedup_posts(posts, seen_posts)
            result.posts.extend(new_posts)
            logger.info("  %d posts (%d nieuw na dedup)", len(posts), len(new_posts))

            if fetch_comments:
                for p_idx, post in enumerate(new_posts, start=1):
                    if progress:
                        progress(
                            "comments",
                            p_idx,
                            len(new_posts),
                            f"Comments voor post {p_idx}/{len(new_posts)} ({label})",
                        )
                    comments = self._fetch_comments(post, kw, max_comments)
                    new_comments = self._dedup_comments(comments, seen_comments)
                    result.comments.extend(new_comments)

        logger.info("Scrape klaar: %s", result.summary)
        return result

    # --------------------------------------------------------------- internals
    def _search(
        self,
        keyword: str,
        subreddit: Optional[str],
        sort: str,
        time_filter: str,
        max_posts: int,
    ) -> List[Post]:
        if self.config.data_source == "rss":
            from . import rss_client

            posts = rss_client.search_posts(
                self.client, keyword, subreddit, sort, time_filter,
                base_url=self.config.reddit_base_url,
            )
            return posts[:max_posts]

        base = self.config.reddit_base_url  # voor klikbare permalinks
        url = self._search_url(subreddit)

        collected: List[Post] = []
        after: Optional[str] = None
        while len(collected) < max_posts:
            self._refresh_token()
            limit = min(PAGE_SIZE, max_posts - len(collected))
            params: Dict[str, object] = {
                "q": keyword,
                "sort": sort,
                "t": time_filter,
                "limit": limit,
                "raw_json": 1,
            }
            if subreddit:
                params["restrict_sr"] = 1
            if after:
                params["after"] = after

            payload = self.client.get_json(url, params=params)
            if payload is None:
                # JSON faalde -> HTML-fallback (alleen direct-modus, eerste pagina).
                if not collected and not self._api:
                    collected.extend(self._html_fallback(keyword, subreddit, sort, time_filter))
                break

            page = parse_post_listing(
                payload, keyword=keyword, source_url=url, base_url=base
            )
            if not page:
                break
            collected.extend(page)

            after = self._next_after(payload)
            if not after:
                break

        return collected[:max_posts]

    def _html_fallback(
        self, keyword: str, subreddit: Optional[str], sort: str, time_filter: str
    ) -> List[Post]:
        base = "https://old.reddit.com"
        if subreddit:
            url = f"{base}/r/{subreddit}/search"
        else:
            url = f"{base}/search"
        params = {"q": keyword, "sort": sort, "t": time_filter}
        if subreddit:
            params["restrict_sr"] = "1"
        html = self.client.get_text(url, params=params)
        if not html:
            return []
        logger.info("JSON faalde; HTML-fallback gebruikt voor '%s'.", keyword)
        return parse_html_search(html, keyword=keyword, source_url=url, base_url=base)

    def _fetch_comments(
        self, post: Post, keyword: str, max_comments: int
    ) -> List[Comment]:
        if not post.permalink:
            return []
        if self.config.data_source == "rss":
            from . import rss_client

            return rss_client.fetch_comments(
                self.client, post, keyword, post.subreddit, max_comments,
                base_url=self.config.reddit_base_url,
            )
        base = self.config.reddit_base_url
        self._refresh_token()
        url = self._comments_url(post.permalink)
        params = {"limit": min(PAGE_SIZE, max_comments), "raw_json": 1, "sort": "top"}
        payload = self.client.get_json(url, params=params)
        if payload is None:
            return []
        return parse_comments(
            payload,
            post_id=post.post_id,
            subreddit=post.subreddit,
            keyword=keyword,
            source_url=url,
            base_url=base,
            max_comments=max_comments,
        )

    @staticmethod
    def _next_after(payload: object) -> Optional[str]:
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                return data.get("after")
        return None

    @staticmethod
    def _dedup_posts(posts: List[Post], seen: Set[str]) -> List[Post]:
        out: List[Post] = []
        for p in posts:
            key = p.dedup_key
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    @staticmethod
    def _dedup_comments(comments: List[Comment], seen: Set[str]) -> List[Comment]:
        out: List[Comment] = []
        for c in comments:
            key = c.dedup_key
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    @staticmethod
    def _validate(value: str, allowed: Set[str], default: str) -> str:
        value = (value or "").strip().lower()
        if value not in allowed:
            logger.warning("Ongeldige waarde '%s'; gebruik '%s'.", value, default)
            return default
        return value
