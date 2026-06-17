"""Schoonmaken en normaliseren van verzamelde Reddit-content.

Verwijdert lege/deleted/removed content, normaliseert tekst, ruimt HTML en
whitespace op, herkent taal, filtert spam, dedupliceert en groepeert per
subreddit/keyword/thread.
"""

from __future__ import annotations

import re
from collections import defaultdict
from html import unescape
from typing import Dict, Iterable, List, Optional

from .parser import Comment, Post
from .utils import get_logger, stable_hash

logger = get_logger()

# Markers die Reddit gebruikt voor verwijderde content.
_DELETED_MARKERS = {"[deleted]", "[removed]", "[verwijderd]", "deleted", "removed"}

# Eenvoudige spam-signalen (best-effort).
_SPAM_PATTERNS = [
    re.compile(r"\b(?:buy|order)\s+now\b", re.I),
    re.compile(r"\b(?:click|tap)\s+here\b", re.I),
    re.compile(r"\b(?:discount|promo)\s*code\b", re.I),
    re.compile(r"https?://\S+", re.I),  # gebruikt alleen als ratio te hoog is
    re.compile(r"\b(?:dm me|pm me|whatsapp|telegram)\b", re.I),
]

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MULTISPACE_RE = re.compile(r"[ \t ]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def is_deleted(text: Optional[str]) -> bool:
    if not text:
        return True
    return text.strip().lower() in _DELETED_MARKERS


def clean_text(text: Optional[str], strip_urls: bool = False) -> str:
    """Normaliseer vrije tekst: unescape HTML, strip tags, fix whitespace."""
    if not text:
        return ""
    text = unescape(text)
    # Markdown-links -> alleen de zichtbare tekst.
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    if strip_urls:
        text = _URL_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTISPACE_RE.sub(" ", text)
    text = _MULTINEWLINE_RE.sub("\n\n", text)
    return text.strip()


def detect_language(text: str) -> Optional[str]:
    """Herken de taal van een tekst (None als onbekend / langdetect ontbreekt)."""
    if not text or len(text) < 12:
        return None
    try:
        from langdetect import detect, LangDetectException  # type: ignore
    except ImportError:
        return None
    try:
        return detect(text)
    except Exception:  # LangDetectException en alle randgevallen
        return None


def looks_like_spam(text: str) -> bool:
    """Heuristische spamdetectie. Conservatief om false positives te beperken."""
    if not text:
        return False
    hits = 0
    for pat in _SPAM_PATTERNS[:-1]:  # url-pattern apart behandelen
        if pat.search(text):
            hits += 1
    # Veel URL's t.o.v. tekst is een sterk spam-signaal.
    urls = _URL_RE.findall(text)
    words = max(1, len(text.split()))
    if len(urls) >= 3 and (len(urls) / words) > 0.2:
        hits += 1
    return hits >= 2


def clean_comments(
    comments: Iterable[Comment],
    min_length: int = 2,
    drop_spam: bool = True,
    target_language: Optional[str] = None,
) -> List[Comment]:
    """Filter en normaliseer comments.

    * verwijdert lege / deleted / removed comments;
    * normaliseert de body;
    * filtert spam (optioneel);
    * filtert op taal (optioneel, bv. 'en' of 'nl');
    * dedupliceert op genormaliseerde inhoud.
    """
    seen_hashes = set()
    out: List[Comment] = []
    removed = 0
    for c in comments:
        if is_deleted(c.body):
            removed += 1
            continue
        body = clean_text(c.body)
        if len(body) < min_length:
            removed += 1
            continue
        if drop_spam and looks_like_spam(body):
            removed += 1
            continue
        if target_language:
            lang = detect_language(body)
            if lang and lang != target_language:
                removed += 1
                continue
        h = stable_hash(body.lower())
        if h in seen_hashes:
            removed += 1
            continue
        seen_hashes.add(h)
        c.body = body
        out.append(c)
    logger.info("Comments opgeschoond: %d behouden, %d verwijderd.", len(out), removed)
    return out


def clean_posts(
    posts: Iterable[Post],
    drop_spam: bool = True,
    target_language: Optional[str] = None,
) -> List[Post]:
    """Normaliseer posts; verwijder deleted/spam en dedupliceer op titel+tekst."""
    seen_hashes = set()
    out: List[Post] = []
    removed = 0
    for p in posts:
        title = clean_text(p.title)
        selftext = clean_text(p.selftext)
        combined = f"{title}\n{selftext}".strip()
        if not combined or is_deleted(selftext) and not title:
            removed += 1
            continue
        if drop_spam and looks_like_spam(combined):
            removed += 1
            continue
        if target_language:
            lang = detect_language(combined)
            if lang and lang != target_language:
                removed += 1
                continue
        h = stable_hash(title.lower(), selftext.lower())
        if h in seen_hashes:
            removed += 1
            continue
        seen_hashes.add(h)
        p.title = title
        p.selftext = selftext
        out.append(p)
    logger.info("Posts opgeschoond: %d behouden, %d verwijderd.", len(out), removed)
    return out


# ----------------------------------------------------------------- groeperen
def group_by_subreddit(comments: Iterable[Comment]) -> Dict[str, List[Comment]]:
    groups: Dict[str, List[Comment]] = defaultdict(list)
    for c in comments:
        groups[c.subreddit or "onbekend"].append(c)
    return dict(groups)


def group_by_keyword(comments: Iterable[Comment]) -> Dict[str, List[Comment]]:
    groups: Dict[str, List[Comment]] = defaultdict(list)
    for c in comments:
        groups[c.keyword or "onbekend"].append(c)
    return dict(groups)


def group_by_thread(comments: Iterable[Comment]) -> Dict[str, List[Comment]]:
    groups: Dict[str, List[Comment]] = defaultdict(list)
    for c in comments:
        groups[c.post_id or "onbekend"].append(c)
    return dict(groups)
