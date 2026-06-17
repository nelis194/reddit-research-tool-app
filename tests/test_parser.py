"""Tests voor de parser (Reddit JSON -> modellen, zonder gebruikersdata)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.parser import parse_comments, parse_post_listing  # noqa: E402


SEARCH_PAYLOAD = {
    "kind": "Listing",
    "data": {
        "after": "t3_abc",
        "children": [
            {
                "kind": "t3",
                "data": {
                    "id": "abc",
                    "subreddit": "skincare",
                    "title": "Best routine?",
                    "selftext": "I struggle with acne",
                    "url": "https://reddit.com/x",
                    "score": 42,
                    "num_comments": 7,
                    "created_utc": 1_700_000_000,
                    "permalink": "/r/skincare/comments/abc/best_routine/",
                    "link_flair_text": "Question",
                    "author": "someuser",  # moet genegeerd worden
                },
            }
        ],
    },
}

COMMENT_PAYLOAD = [
    {"kind": "Listing", "data": {"children": []}},  # de post-listing
    {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "link_id": "t3_abc",
                        "parent_id": "t3_abc",
                        "body": "Tretinoin worked for me",
                        "score": 10,
                        "created_utc": 1_700_000_500,
                        "depth": 0,
                        "subreddit": "skincare",
                        "permalink": "/r/skincare/comments/abc/_/c1/",
                        "author": "anotheruser",  # moet genegeerd worden
                        "replies": {
                            "kind": "Listing",
                            "data": {
                                "children": [
                                    {
                                        "kind": "t1",
                                        "data": {
                                            "id": "c2",
                                            "link_id": "t3_abc",
                                            "parent_id": "t1_c1",
                                            "body": "Same here",
                                            "score": 3,
                                            "created_utc": 1_700_000_600,
                                            "depth": 1,
                                        },
                                    },
                                    {"kind": "more", "data": {"id": "_"}},
                                ]
                            },
                        },
                    },
                }
            ]
        },
    },
]


def test_parse_post_listing_basic():
    posts = parse_post_listing(SEARCH_PAYLOAD, keyword="acne", source_url="u")
    assert len(posts) == 1
    p = posts[0]
    assert p.post_id == "abc"
    assert p.subreddit == "skincare"
    assert p.score == 42
    assert p.flair == "Question"
    assert p.permalink.endswith("/best_routine/")
    # Geen gebruikersdata in het model.
    assert not hasattr(p, "author")
    assert "author" not in p.to_dict()


def test_parse_comments_flattens_tree():
    comments = parse_comments(COMMENT_PAYLOAD, post_id="abc", keyword="acne")
    ids = sorted(c.comment_id for c in comments)
    assert ids == ["c1", "c2"]
    c2 = next(c for c in comments if c.comment_id == "c2")
    assert c2.depth == 1
    assert c2.parent_id == "c1"  # prefix t1_ verwijderd
    # 'more' kind wordt overgeslagen.
    assert all(c.body for c in comments)


def test_parse_comments_respects_max():
    comments = parse_comments(COMMENT_PAYLOAD, post_id="abc", max_comments=1)
    assert len(comments) == 1


def test_no_user_fields_in_dict():
    comments = parse_comments(COMMENT_PAYLOAD, post_id="abc")
    for c in comments:
        d = c.to_dict()
        for banned in ("author", "author_fullname", "user", "karma"):
            assert banned not in d
