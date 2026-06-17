"""Tests voor de cleaner."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.cleaner import (  # noqa: E402
    clean_comments,
    clean_posts,
    clean_text,
    group_by_subreddit,
    is_deleted,
    looks_like_spam,
)
from src.parser import Comment, Post  # noqa: E402


def _comment(body, **kw):
    base = dict(
        comment_id=None,
        post_id="p1",
        parent_id=None,
        score=1,
        created_date=None,
        depth=0,
        permalink=None,
        keyword="kw",
        subreddit="test",
        source_url=None,
    )
    base.update(kw)
    return Comment(body=body, **base)


def test_is_deleted():
    assert is_deleted("[deleted]")
    assert is_deleted("[removed]")
    assert is_deleted("")
    assert is_deleted(None)
    assert not is_deleted("normale tekst")


def test_clean_text_html_and_whitespace():
    raw = "<p>Hello   &amp; world</p>\n\n\n\nmore"
    out = clean_text(raw)
    assert "&amp;" not in out
    assert "<p>" not in out
    assert "Hello & world" in out
    assert "\n\n\n" not in out


def test_clean_text_markdown_link():
    out = clean_text("check [this link](https://example.com) please")
    assert "this link" in out
    assert "https://example.com" not in out


def test_clean_comments_removes_deleted_and_dups():
    comments = [
        _comment("[deleted]"),
        _comment("This product really helped my skin a lot"),
        _comment("This product really helped my skin a lot"),  # duplicate
        _comment("x"),  # te kort
    ]
    cleaned = clean_comments(comments, min_length=3)
    bodies = [c.body for c in cleaned]
    assert len(cleaned) == 1
    assert bodies[0].startswith("This product")


def test_clean_posts_dedup():
    posts = [
        Post(
            post_id="1", subreddit="s", title="Best supplement", selftext="text here",
            url=None, score=5, num_comments=2, created_date=None, permalink=None,
            keyword="kw", flair=None, source_url=None,
        ),
        Post(
            post_id="2", subreddit="s", title="Best supplement", selftext="text here",
            url=None, score=3, num_comments=1, created_date=None, permalink=None,
            keyword="kw", flair=None, source_url=None,
        ),
    ]
    cleaned = clean_posts(posts)
    assert len(cleaned) == 1


def test_looks_like_spam():
    spam = "BUY NOW! Click here for a promo code, DM me on telegram"
    assert looks_like_spam(spam)
    assert not looks_like_spam("I really like this approach to skincare")


def test_group_by_subreddit():
    comments = [_comment("a", subreddit="x"), _comment("b", subreddit="y"), _comment("c", subreddit="x")]
    groups = group_by_subreddit(comments)
    assert set(groups.keys()) == {"x", "y"}
    assert len(groups["x"]) == 2
