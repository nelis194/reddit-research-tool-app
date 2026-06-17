"""Reddit-databron via publieke RSS/Atom-feeds.

Reddit blokkeert de JSON-endpoints vaak met 403, maar de publieke ``.rss``-feeds
zijn (op het moment van schrijven) wél bereikbaar zonder login of proxy. Dit is
een officieel aangeboden syndicatie-formaat.

Beperkingen t.o.v. de JSON-API:
* ~25 entries per feed, geen paginatie (geen ``after``-token);
* geen score / num_comments (Atom levert die niet);
* comment-structuur (parent/depth) is niet beschikbaar.

We halen er uit wat er is: titel, tekst, permalink, subreddit, datum. Géén
gebruikersdata (auteur wordt genegeerd).
"""

from __future__ import annotations

import re
from typing import List, Optional

from .config import Config
from .parser import Comment, Post
from .utils import get_logger
from .web_client import WebClient

logger = get_logger()

_POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/", re.I)
_SUBREDDIT_RE = re.compile(r"/r/([^/]+)/", re.I)
_COMMENT_ID_RE = re.compile(r"/comments/[a-z0-9]+/[^/]*/([a-z0-9]+)/?", re.I)


def _soup(text: str):
    from bs4 import BeautifulSoup

    # lxml's XML-parser; Atom-tags zijn vindbaar op lokale naam (title, entry...).
    return BeautifulSoup(text, "xml")


def _entry_text(entry, tag: str) -> str:
    el = entry.find(tag)
    return el.get_text() if el is not None else ""


def _entry_link(entry) -> Optional[str]:
    link = entry.find("link")
    if link is None:
        return None
    return link.get("href") or (link.get_text() or None)


# sort -> subreddit-listing dat wél bereikbaar is via RSS.
_LISTING_FOR_SORT = {
    "new": "new",
    "hot": "hot",
    "top": "top",
    "relevance": "top",
    "comments": "top",
}


def search_posts(
    client: WebClient,
    keyword: str,
    subreddit: Optional[str],
    sort: str,
    time_filter: str,
    base_url: str = "https://www.reddit.com",
) -> List[Post]:
    """Haal posts op via RSS.

    * Zónder subreddit: de globale zoekfeed (``/search.rss?q=...``) — geeft echte
      posts voor het keyword over heel Reddit.
    * Mét subreddit: de listing-feed (``/r/sub/top.rss`` etc.), want de
      subreddit-zoekfeed geeft 403. We filteren die posts lokaal op het keyword;
      levert dat niets op, dan houden we alle posts uit de niche.
    """
    if subreddit:
        listing = _LISTING_FOR_SORT.get(sort, "top")
        url = f"{base_url}/r/{subreddit}/{listing}.rss"
        params = {"limit": 25}
        if listing == "top":
            params["t"] = time_filter
    else:
        url = f"{base_url}/search.rss"
        params = {"q": keyword, "sort": sort, "t": time_filter, "limit": 25}

    text = client.get_text(url, params=params)
    if not text:
        return []

    soup = _soup(text)
    posts: List[Post] = []
    for entry in soup.find_all("entry"):
        link = _entry_link(entry)
        if not link:
            continue
        post_id_match = _POST_ID_RE.search(link)
        # In de globale zoekfeed zitten ook subreddit-resultaten (geen /comments/);
        # die slaan we over — we willen alleen echte posts.
        if post_id_match is None:
            continue
        sub_match = _SUBREDDIT_RE.search(link)
        posts.append(
            Post(
                post_id=post_id_match.group(1),
                subreddit=(subreddit or (sub_match.group(1) if sub_match else None)),
                title=_entry_text(entry, "title").strip(),
                selftext=_entry_text(entry, "content").strip(),
                url=link,
                score=0,  # niet beschikbaar via RSS
                num_comments=0,
                created_date=_entry_text(entry, "updated") or _entry_text(entry, "published") or None,
                permalink=link,
                keyword=keyword,
                flair=None,
                source_url=url,
            )
        )

    # Lokale keyword-filter voor subreddit-listings.
    if subreddit and keyword:
        kw_terms = [w for w in re.split(r"\s+", keyword.lower()) if len(w) > 2]
        if kw_terms:
            filtered = [
                p for p in posts
                if any(t in (p.title + " " + p.selftext).lower() for t in kw_terms)
            ]
            if filtered:  # alleen filteren als er iets overblijft
                posts = filtered

    logger.info("RSS: %d posts voor '%s'%s", len(posts), keyword,
                f" in r/{subreddit}" if subreddit else "")
    return posts


def fetch_comments(
    client: WebClient,
    post: Post,
    keyword: str,
    subreddit: Optional[str],
    max_comments: int,
    base_url: str = "https://www.reddit.com",
) -> List[Comment]:
    """Haal comments op via de RSS-feed van een post (best-effort)."""
    if not post.permalink:
        return []
    url = post.permalink.rstrip("/") + "/.rss"
    text = client.get_text(url)
    if not text:
        return []

    soup = _soup(text)
    comments: List[Comment] = []
    for entry in soup.find_all("entry"):
        if len(comments) >= max_comments:
            break
        link = _entry_link(entry)
        body = _entry_text(entry, "content").strip()
        if not body:
            continue
        cid_match = _COMMENT_ID_RE.search(link or "")
        comments.append(
            Comment(
                comment_id=cid_match.group(1) if cid_match else None,
                post_id=post.post_id,
                parent_id=None,       # niet beschikbaar via RSS
                body=body,
                score=0,              # niet beschikbaar via RSS
                created_date=_entry_text(entry, "updated") or None,
                depth=0,
                permalink=link,
                keyword=keyword,
                subreddit=subreddit or post.subreddit,
                source_url=url,
            )
        )
    return comments
