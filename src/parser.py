"""Parsen van Reddit-data naar nette datamodellen.

Belangrijk: dit module verzamelt **geen gebruikersdata**. Usernames, user-ids,
karma, profiel- en accountinformatie worden bewust genegeerd. We bewaren
uitsluitend inhoud van discussies (titels, teksten, scores, structuur).

Reddit exposeert publieke JSON door ``.json`` aan een URL te plakken. Deze
parser begrijpt die listing-structuur. Voor het geval Reddit alleen HTML
teruggeeft is er een BeautifulSoup-fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .utils import epoch_to_iso, now_iso, safe_int, stable_hash

# Velden die we expliciet NOOIT overnemen (privacy / geen gebruikersdata).
_BANNED_FIELDS = {
    "author",
    "author_fullname",
    "author_flair_text",
    "author_premium",
    "author_patreon_flair",
    "user_reports",
    "mod_reports",
    "likes",
    "saved",
}


@dataclass
class Post:
    """Een Reddit-post, vrij van gebruikersdata."""

    post_id: Optional[str]
    subreddit: Optional[str]
    title: str
    selftext: str
    url: Optional[str]
    score: int
    num_comments: int
    created_date: Optional[str]
    permalink: Optional[str]
    keyword: Optional[str]
    flair: Optional[str]
    source_url: Optional[str]
    collected_at: str = field(default_factory=now_iso)

    @property
    def dedup_key(self) -> str:
        return self.post_id or stable_hash(self.title, self.selftext, self.subreddit)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "subreddit": self.subreddit,
            "title": self.title,
            "selftext": self.selftext,
            "url": self.url,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_date": self.created_date,
            "permalink": self.permalink,
            "keyword": self.keyword,
            "flair": self.flair,
            "source_url": self.source_url,
            "collected_at": self.collected_at,
        }


@dataclass
class Comment:
    """Een Reddit-comment, vrij van gebruikersdata."""

    comment_id: Optional[str]
    post_id: Optional[str]
    parent_id: Optional[str]
    body: str
    score: int
    created_date: Optional[str]
    depth: int
    permalink: Optional[str]
    keyword: Optional[str]
    subreddit: Optional[str]
    source_url: Optional[str]
    collected_at: str = field(default_factory=now_iso)

    @property
    def dedup_key(self) -> str:
        return self.comment_id or stable_hash(self.body, self.post_id, self.parent_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "parent_id": self.parent_id,
            "body": self.body,
            "score": self.score,
            "created_date": self.created_date,
            "depth": self.depth,
            "permalink": self.permalink,
            "keyword": self.keyword,
            "subreddit": self.subreddit,
            "source_url": self.source_url,
            "collected_at": self.collected_at,
        }


def _absolute_permalink(base_url: str, permalink: Optional[str]) -> Optional[str]:
    if not permalink:
        return None
    if permalink.startswith("http"):
        return permalink
    return f"{base_url.rstrip('/')}{permalink}"


def parse_post_listing(
    payload: Any,
    keyword: Optional[str] = None,
    source_url: Optional[str] = None,
    base_url: str = "https://www.reddit.com",
) -> List[Post]:
    """Parse een Reddit-listing (search/subreddit) naar ``Post``-objecten.

    Accepteert zowel de ``{"data": {"children": [...]}}``-structuur als een
    losse lijst van children.
    """
    children = _extract_children(payload)
    posts: List[Post] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        if child.get("kind") not in (None, "t3"):
            # t3 = link/post. Andere kinds (comments, more) negeren we hier.
            continue
        data = child.get("data", child)
        if not isinstance(data, dict):
            continue
        posts.append(
            Post(
                post_id=data.get("id"),
                subreddit=data.get("subreddit"),
                title=(data.get("title") or "").strip(),
                selftext=(data.get("selftext") or "").strip(),
                url=data.get("url") or data.get("url_overridden_by_dest"),
                score=safe_int(data.get("score"), 0),
                num_comments=safe_int(data.get("num_comments"), 0),
                created_date=epoch_to_iso(data.get("created_utc")),
                permalink=_absolute_permalink(base_url, data.get("permalink")),
                keyword=keyword,
                flair=data.get("link_flair_text"),
                source_url=source_url,
            )
        )
    return posts


def parse_comments(
    payload: Any,
    post_id: Optional[str] = None,
    subreddit: Optional[str] = None,
    keyword: Optional[str] = None,
    source_url: Optional[str] = None,
    base_url: str = "https://www.reddit.com",
    max_comments: Optional[int] = None,
) -> List[Comment]:
    """Plat een (geneste) Reddit comment-tree af naar ``Comment``-objecten.

    Reddit geeft op ``/comments/<id>.json`` een lijst van twee listings terug:
    [0] = de post, [1] = de comments. We accepteren ook een losse comment-listing.
    """
    comment_listing: Any = payload
    if isinstance(payload, list) and len(payload) >= 2:
        comment_listing = payload[1]

    results: List[Comment] = []

    def _walk(node: Any, depth: int) -> None:
        if max_comments is not None and len(results) >= max_comments:
            return
        children = _extract_children(node)
        for child in children:
            if max_comments is not None and len(results) >= max_comments:
                return
            if not isinstance(child, dict):
                continue
            kind = child.get("kind")
            data = child.get("data", {})
            if kind == "more" or not isinstance(data, dict):
                continue
            body = (data.get("body") or "").strip()
            if body or data.get("id"):
                results.append(
                    Comment(
                        comment_id=data.get("id"),
                        post_id=post_id or _strip_prefix(data.get("link_id")),
                        parent_id=_strip_prefix(data.get("parent_id")),
                        body=body,
                        score=safe_int(data.get("score"), 0),
                        created_date=epoch_to_iso(data.get("created_utc")),
                        depth=safe_int(data.get("depth"), depth),
                        permalink=_absolute_permalink(base_url, data.get("permalink")),
                        keyword=keyword,
                        subreddit=subreddit or data.get("subreddit"),
                        source_url=source_url,
                    )
                )
            # Recurse in replies.
            replies = data.get("replies")
            if isinstance(replies, dict):
                _walk(replies, depth + 1)

    _walk(comment_listing, 0)
    return results


def parse_html_search(
    html: str,
    keyword: Optional[str] = None,
    source_url: Optional[str] = None,
    base_url: str = "https://old.reddit.com",
) -> List[Post]:
    """BeautifulSoup-fallback: schraap posts uit old.reddit.com HTML.

    Wordt alleen gebruikt als de JSON-route faalt. Best-effort.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        return []

    soup = BeautifulSoup(html, "lxml")
    posts: List[Post] = []
    for thing in soup.select("div.thing[data-fullname^='t3_']"):
        title_el = thing.select_one("a.title")
        subreddit = thing.get("data-subreddit")
        permalink = thing.get("data-permalink")
        score = thing.get("data-score")
        comments = thing.get("data-comments-count")
        post_id = (thing.get("data-fullname") or "").replace("t3_", "") or None
        posts.append(
            Post(
                post_id=post_id,
                subreddit=subreddit,
                title=(title_el.get_text(strip=True) if title_el else "").strip(),
                selftext="",
                url=title_el.get("href") if title_el else None,
                score=safe_int(score, 0),
                num_comments=safe_int(comments, 0),
                created_date=None,
                permalink=_absolute_permalink(base_url, permalink),
                keyword=keyword,
                flair=None,
                source_url=source_url,
            )
        )
    return posts


# --------------------------------------------------------------------- helpers
def _extract_children(payload: Any) -> List[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("children"), list):
            return data["children"]
        if isinstance(payload.get("children"), list):
            return payload["children"]
    if isinstance(payload, list):
        return payload
    return []


def _strip_prefix(value: Optional[str]) -> Optional[str]:
    """Verwijder Reddit fullname-prefix (t1_, t3_, ...) -> kale id."""
    if not value or not isinstance(value, str):
        return value
    if "_" in value and value[:2] in {"t1", "t2", "t3", "t4", "t5", "t6"}:
        return value.split("_", 1)[1]
    return value
