"""Tests voor de lokale analyse-pipeline."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analyzer import Analyzer  # noqa: E402


DOCS = [
    "I struggle with acne and it is so frustrating. Nothing seems to work.",
    "Tretinoin worked great for me and solved my breakouts. Highly recommend it.",
    "I tried CeraVe but it didn't work and made it worse. Waste of money.",
    "I wish I could find an affordable routine. It's too expensive for me on a budget.",
    "As a beginner I have no idea where to start with skincare. Any recommendations?",
    "Why is everything so confusing? I'm so tired of conflicting advice.",
    "Does retinol cause purging? How long until it works?",
    "Used to have terrible skin, now after a few months my skin is clear.",
]


def test_analyze_returns_categories():
    result = Analyzer(keyword_context=["skincare"]).analyze(DOCS)
    assert result.document_count == len(DOCS)
    assert result.top_pain_points, "verwacht pijnpunten"
    assert result.top_frustrations, "verwacht frustraties"
    assert result.top_successful_solutions, "verwacht geslaagde oplossingen"
    assert result.top_failed_solutions, "verwacht mislukte oplossingen"


def test_sentiment_present():
    result = Analyzer().analyze(DOCS)
    assert "polarity" in result.sentiment
    assert "label" in result.sentiment


def test_personas_detected():
    result = Analyzer().analyze(DOCS)
    personas = {p["persona"] for p in result.persona_clusters}
    # 'beginner' en 'prijsgevoelig' zitten in de docs.
    assert "beginner" in personas
    assert "prijsgevoelig" in personas


def test_faqs_extracted():
    result = Analyzer().analyze(DOCS)
    questions = [f["question"] for f in result.faqs]
    assert any("?" in q for q in questions)


def test_before_after_detected():
    result = Analyzer().analyze(DOCS)
    assert result.before_after, "verwacht een before/after quote"


def test_common_words_and_phrases():
    result = Analyzer().analyze(DOCS)
    assert result.common_words
    assert all("word" in w and "count" in w for w in result.common_words)
    assert isinstance(result.common_phrases, list)


def test_tfidf_scores():
    result = Analyzer().analyze(DOCS)
    assert result.tfidf_terms
    assert all("term" in t and "score" in t for t in result.tfidf_terms)


def test_medical_disclaimer_triggers():
    medical_docs = [
        "My cholesterol and artery plaque improved after taking this supplement daily.",
        "The doctor said my blood pressure and statin dosage need adjusting.",
    ]
    result = Analyzer(keyword_context=["artery plaque"]).analyze(medical_docs)
    assert result.is_medical
    assert result.disclaimer
    assert "geen medisch advies" in result.disclaimer.lower()


def test_empty_documents():
    result = Analyzer().analyze([])
    assert result.document_count == 0
    assert result.top_pain_points == []


def test_competitor_matching():
    docs = ["I switched from BrandX to BrandY and BrandY is better."]
    result = Analyzer().analyze(docs, competitor_terms=["BrandX", "BrandY"])
    terms = {c["term"]: c["count"] for c in result.mentioned_competitors}
    assert terms.get("BrandY", 0) >= 2
