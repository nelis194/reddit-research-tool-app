"""Generieke, taal-onafhankelijke analyse-pipeline (zonder LLM).

Werkt op een lijst tekstfragmenten (post-titels/selftext + comments) en levert
een ``AnalysisResult`` met o.a. pijnpunten, frustraties, gewenste uitkomsten,
geslaagde/mislukte oplossingen, genoemde producten/merken, voice-of-customer
quotes, woord-/zin-frequenties, TF-IDF, sentiment, persona-clusters, koop-
motieven/-bezwaren, content angles, ad hooks, FAQ's, before/after en trends.

Alle extractie is heuristisch (regex + keyword-patronen + n-grams + TF-IDF).
Met een OpenAI-key kan ``llm_analyzer`` deze output verrijken/overschrijven.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from .utils import get_logger, truncate

logger = get_logger()

# --------------------------------------------------------------------- lexicons
# Engelstalige stopwoorden + een handvol NL stopwoorden (generiek bruikbaar).
STOPWORDS = set(
    """
    a an the and or but if then than so because as of at by for with about against
    between into through during before after above below to from up down in out on off
    over under again further once here there all any both each few more most other some
    such no nor not only own same too very can will just don should now i me my we our you
    your he she it they them this that these those is are was were be been being have has
    had do does did doing would could should ll re ve m s t d don't im it's that's
    de het een en van te dat die in op voor met als maar ook nog wel niet je ik we ze
    om aan bij door uit naar tot zo wat hoe heb heeft was waren zijn worden wordt
    """.split()
)

POSITIVE_WORDS = set(
    """
    great love amazing awesome excellent perfect best helped works worked working
    recommend recommended improved improvement better good happy glad solved solution
    effective worth wonderful fantastic incredible reliable smooth easy fixed cured
    relief relieved success successful win winning enjoy enjoyed favorite favourite
    """.split()
)

NEGATIVE_WORDS = set(
    """
    hate terrible awful worst bad horrible useless broken waste wasted disappointed
    disappointing frustrating frustrated annoying annoyed painful pain problem problems
    issue issues fail failed failing scam ripoff expensive overpriced confusing
    difficult hard struggle struggling worse worsened ineffective regret avoid garbage
    nightmare angry sucks crap junk
    """.split()
)

# Cue-frases voor categorie-extractie. Patroon -> categorie.
PAIN_CUES = [
    r"\bstruggl\w+\b", r"\bcan'?t\s+\w+", r"\bhard\s+to\b", r"\bdifficult\b",
    r"\bpainful\b", r"\bhurts?\b", r"\bsuffer\w*", r"\bproblem\w*", r"\bissues?\b",
    r"\btrouble\b", r"\bunable to\b", r"\bkeeps?\s+\w+ing\b",
]
FRUSTRATION_CUES = [
    r"\bfrustrat\w+", r"\bannoy\w+", r"\bsick\s+of\b", r"\btired\s+of\b",
    r"\bfed up\b", r"\bhate\b", r"\bso\s+(?:bad|annoying|frustrating)\b",
    r"\bwhy\s+(?:do|does|is|can'?t)\b", r"\bdriving me (?:crazy|nuts)\b",
]
DESIRE_CUES = [
    r"\bi\s+wish\b", r"\bi\s+want\b", r"\bi\s+need\b", r"\blooking for\b",
    r"\bhope\s+to\b", r"\bwould love\b", r"\bif only\b", r"\bgoal\s+is\b",
    r"\bgothat\b", r"\bplease recommend\b", r"\bany recommendations?\b",
]
FAILED_CUES = [
    r"\bdidn'?t work\b", r"\bdoesn'?t work\b", r"\bstopped working\b",
    r"\bno\s+(?:luck|results?|effect|improvement)\b", r"\bwaste of\b",
    r"\btried\s+\w+\s+but\b", r"\bgave up on\b", r"\bmade it worse\b",
]
SUCCESS_CUES = [
    r"\bworked (?:great|well|for me|wonders)\b", r"\bsolved\b", r"\bfixed\b",
    r"\bgame changer\b", r"\bhighly recommend\b", r"\bbest\s+\w+\s+(?:i|ive|i've)\b",
    r"\bsaved (?:me|my)\b", r"\bhelped (?:me|a lot)\b", r"\bcured\b",
]
OBJECTION_CUES = [
    r"\btoo expensive\b", r"\bnot worth\b", r"\bcan'?t afford\b", r"\boverpriced\b",
    r"\bnot sure (?:if|whether)\b", r"\bafraid (?:of|that)\b", r"\bworried about\b",
    r"\bskeptical\b", r"\bdon'?t trust\b", r"\bisn'?t it\b.*\bexpensive\b",
    r"\bhesitant\b", r"\bwhat'?s the catch\b",
]
MOTIVATION_CUES = [
    r"\bi (?:bought|purchased|switched to|chose)\b", r"\bworth (?:it|the money|every penny)\b",
    r"\bdecided to\b", r"\bso glad i\b", r"\bbecause it\b", r"\bmain reason\b",
    r"\bwhat made me\b", r"\bconvinced me\b",
]

# Medische/gezondheids-trigger voor disclaimer.
MEDICAL_TERMS = set(
    """
    plaque artery arteries cholesterol statin supplement supplements vitamin vitamins
    dose dosage mg disease symptom symptoms diagnosis treatment cure medication
    medicine drug drugs side effect side-effects doctor physician clinical health
    blood pressure diabetes cancer skin acne eczema rosacea inflammation gut probiotic
    hormone testosterone thyroid depression anxiety adhd insomnia pain therapy
    """.split()
)

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Eenvoudige product/merk-detectie: hoofdletter-initiaal tokens (CeraVe, NAC,
# Tretinoin). Bewust een SIMPELE, lineaire regex zonder geneste quantifiers —
# de oude variant kon catastrofaal backtracken op grote teksten.
_BRANDISH_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")

# Harde grenzen zodat de analyse nooit vastloopt op grote datasets.
MAX_DOCS = 1500          # max aantal documenten (posts + comments) dat we wegen
MAX_DOC_CHARS = 2000     # max tekens per document
MAX_SENTENCES = 6000     # max aantal zinnen voor cue-extractie


@dataclass
class AnalysisResult:
    """Volledige, serialiseerbare analyse-uitkomst."""

    keyword_context: List[str] = field(default_factory=list)
    document_count: int = 0
    is_medical: bool = False
    disclaimer: Optional[str] = None

    top_pain_points: List[Dict] = field(default_factory=list)
    top_frustrations: List[Dict] = field(default_factory=list)
    top_desired_outcomes: List[Dict] = field(default_factory=list)
    top_failed_solutions: List[Dict] = field(default_factory=list)
    top_successful_solutions: List[Dict] = field(default_factory=list)

    mentioned_products: List[Dict] = field(default_factory=list)
    mentioned_brands: List[Dict] = field(default_factory=list)
    mentioned_competitors: List[Dict] = field(default_factory=list)

    voice_of_customer: Dict[str, List[str]] = field(default_factory=dict)
    common_words: List[Dict] = field(default_factory=list)
    common_phrases: List[Dict] = field(default_factory=list)
    tfidf_terms: List[Dict] = field(default_factory=list)
    sentiment: Dict[str, float] = field(default_factory=dict)

    persona_clusters: List[Dict] = field(default_factory=list)
    buying_objections: List[Dict] = field(default_factory=list)
    buying_motivations: List[Dict] = field(default_factory=list)

    content_angles: List[str] = field(default_factory=list)
    ad_hooks: List[str] = field(default_factory=list)
    faqs: List[Dict] = field(default_factory=list)
    before_after: List[Dict] = field(default_factory=list)
    emerging_trends: List[Dict] = field(default_factory=list)
    recurring_complaints: List[Dict] = field(default_factory=list)
    recurring_compliments: List[Dict] = field(default_factory=list)

    subreddit_distribution: List[Dict] = field(default_factory=list)
    llm_insights: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# Persona-heuristiek: label -> signaalwoorden.
PERSONA_SIGNALS = {
    "beginner": ["beginner", "new to", "just started", "noob", "newbie", "first time", "where do i start", "eli5"],
    "intermediate": ["been doing", "for a few months", "intermediate", "getting better", "next level"],
    "expert": ["years of experience", "advanced", "professional", "i've tested", "in my experience", "pro tip"],
    "prijsgevoelig": ["cheap", "budget", "affordable", "expensive", "can't afford", "on a budget", "best value", "worth the money"],
    "premium koper": ["premium", "high end", "top of the line", "best money can buy", "splurge", "luxury"],
    "diy gebruiker": ["diy", "homemade", "build your own", "do it yourself", "from scratch", "self made"],
    "zakelijk": ["my business", "our team", "company", "clients", "b2b", "enterprise", "for work", "roi"],
    "consument": ["for my family", "at home", "personal use", "for myself", "household"],
}


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s and s.strip()]


def _tokens(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in STOPWORDS and len(t) > 2]


def _matches_any(patterns: List[str], text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in patterns)


def _extract_by_cues(
    sentences: List[str], cues: List[str], limit: int = 15
) -> List[Dict]:
    """Tel zinnen die een cue matchen, groepeer op genormaliseerde sleutelzin."""
    counter: Counter = Counter()
    examples: Dict[str, str] = {}
    for s in sentences:
        if len(s) < 8 or len(s) > 400:
            continue
        if _matches_any(cues, s):
            key = _phrase_key(s)
            counter[key] += 1
            if key not in examples:
                examples[key] = s
    out = []
    for key, count in counter.most_common(limit):
        out.append({"theme": key, "count": count, "example": truncate(examples[key], 240)})
    return out


def _phrase_key(sentence: str) -> str:
    """Comprimeer een zin tot een korte thema-sleutel (content-woorden)."""
    toks = _content_tokens(sentence)
    return " ".join(toks[:6]) if toks else sentence[:40].lower()


def _ngrams(tokens: List[str], n: int) -> List[str]:
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


class Analyzer:
    """Voert de volledige lokale analyse uit op tekst-documenten."""

    def __init__(self, keyword_context: Optional[List[str]] = None):
        self.keyword_context = keyword_context or []

    def analyze(
        self,
        documents: List[str],
        subreddits: Optional[List[str]] = None,
        competitor_terms: Optional[List[str]] = None,
    ) -> AnalysisResult:
        # Begrens de input zodat de analyse altijd snel en stabiel blijft,
        # ook bij duizenden comments. Documenten staan in volgorde posts->comments,
        # dus de cap behoudt alle posts en een ruime steekproef van comments.
        documents = [d.strip()[:MAX_DOC_CHARS] for d in documents if d and d.strip()]
        if len(documents) > MAX_DOCS:
            logger.info("Analyse begrensd tot %d van %d documenten.", MAX_DOCS, len(documents))
            documents = documents[:MAX_DOCS]
        result = AnalysisResult(
            keyword_context=self.keyword_context,
            document_count=len(documents),
        )
        if not documents:
            logger.warning("Geen documenten om te analyseren.")
            return result

        full_text = "\n".join(documents)
        all_sentences = _split_sentences(full_text)
        if len(all_sentences) > MAX_SENTENCES:
            all_sentences = all_sentences[:MAX_SENTENCES]

        # Medisch?
        result.is_medical = self._is_medical(full_text)
        if result.is_medical:
            result.disclaimer = self._medical_disclaimer()

        # Cue-gebaseerde categorieën.
        result.top_pain_points = _extract_by_cues(all_sentences, PAIN_CUES)
        result.top_frustrations = _extract_by_cues(all_sentences, FRUSTRATION_CUES)
        result.top_desired_outcomes = _extract_by_cues(all_sentences, DESIRE_CUES)
        result.top_failed_solutions = _extract_by_cues(all_sentences, FAILED_CUES)
        result.top_successful_solutions = _extract_by_cues(all_sentences, SUCCESS_CUES)
        result.buying_objections = _extract_by_cues(all_sentences, OBJECTION_CUES)
        result.buying_motivations = _extract_by_cues(all_sentences, MOTIVATION_CUES)

        # Producten/merken/concurrenten.
        brands = self._extract_brands(full_text)
        result.mentioned_brands = brands
        result.mentioned_products = brands  # zelfde signaal; gescheiden veld voor UI
        result.mentioned_competitors = self._match_competitors(full_text, competitor_terms or [])

        # Voice of customer.
        result.voice_of_customer = self._voice_of_customer(all_sentences)

        # Woorden / zinnen / TF-IDF.
        result.common_words = self._common_words(documents)
        result.common_phrases = self._common_phrases(full_text)
        result.tfidf_terms = self._tfidf(documents)

        # Sentiment.
        result.sentiment = self._sentiment(full_text)

        # Persona's.
        result.persona_clusters = self._persona_clusters(documents)

        # Afgeleide marketing-output.
        result.content_angles = self._content_angles(result)
        result.ad_hooks = self._ad_hooks(result)
        result.faqs = self._faqs(all_sentences)
        result.before_after = self._before_after(all_sentences)

        # Trends / herhaling.
        result.emerging_trends = result.common_phrases[:10]
        result.recurring_complaints = (result.top_pain_points + result.top_frustrations)[:10]
        result.recurring_compliments = result.top_successful_solutions[:10]

        # Subreddit-distributie.
        if subreddits:
            dist = Counter(s or "onbekend" for s in subreddits)
            result.subreddit_distribution = [
                {"subreddit": k, "count": v} for k, v in dist.most_common(25)
            ]

        logger.info("Lokale analyse klaar over %d documenten.", len(documents))
        return result

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _is_medical(text: str) -> bool:
        low = text.lower()
        hits = sum(1 for term in MEDICAL_TERMS if re.search(rf"\b{re.escape(term)}\b", low))
        return hits >= 2

    @staticmethod
    def _medical_disclaimer() -> str:
        return (
            "⚠️ Disclaimer: Dit onderwerp raakt gezondheid/medische thema's. Alle hier "
            "samengevatte uitspraken zijn **door gebruikers gerapporteerd** en **anekdotisch**. "
            "Ze vormen **geen medisch advies**. Claims zijn niet geverifieerd en resultaten "
            "kunnen per persoon verschillen. Raadpleeg een gekwalificeerde zorgverlener."
        )

    def _extract_brands(self, text: str, limit: int = 25) -> List[Dict]:
        counter: Counter = Counter()
        for m in _BRANDISH_RE.findall(text):
            token = m.strip()
            low = token.lower()
            if low in STOPWORDS or len(token) < 3:
                continue
            # Skip generieke zin-starters: woorden die ook vaak lowercase voorkomen.
            counter[token] += 1
        # Houd alleen termen die meer dan eens voorkomen (ruis-reductie).
        return [
            {"term": term, "count": count}
            for term, count in counter.most_common(limit * 3)
            if count >= 2
        ][:limit]

    @staticmethod
    def _match_competitors(text: str, competitor_terms: List[str]) -> List[Dict]:
        low = text.lower()
        out = []
        for term in competitor_terms:
            t = term.strip().lower()
            if not t:
                continue
            count = len(re.findall(rf"\b{re.escape(t)}\b", low))
            if count:
                out.append({"term": term, "count": count})
        return sorted(out, key=lambda d: d["count"], reverse=True)

    def _voice_of_customer(self, sentences: List[str]) -> Dict[str, List[str]]:
        buckets = {
            "pijnpunten": PAIN_CUES,
            "frustraties": FRUSTRATION_CUES,
            "gewenste_uitkomsten": DESIRE_CUES,
            "koopbezwaren": OBJECTION_CUES,
            "succesverhalen": SUCCESS_CUES,
        }
        voc: Dict[str, List[str]] = {}
        for label, cues in buckets.items():
            quotes = []
            seen = set()
            for s in sentences:
                if 20 <= len(s) <= 300 and _matches_any(cues, s):
                    key = s.lower()[:60]
                    if key in seen:
                        continue
                    seen.add(key)
                    quotes.append(truncate(s, 280))
                if len(quotes) >= 12:
                    break
            voc[label] = quotes
        return voc

    def _common_words(self, documents: List[str], limit: int = 40) -> List[Dict]:
        counter: Counter = Counter()
        for doc in documents:
            counter.update(_content_tokens(doc))
        return [{"word": w, "count": c} for w, c in counter.most_common(limit)]

    def _common_phrases(self, text: str, limit: int = 30) -> List[Dict]:
        tokens = _content_tokens(text)
        counter: Counter = Counter()
        for n in (2, 3):
            counter.update(_ngrams(tokens, n))
        return [
            {"phrase": p, "count": c}
            for p, c in counter.most_common(limit)
            if c >= 2
        ]

    def _tfidf(self, documents: List[str], limit: int = 30) -> List[Dict]:
        """Eenvoudige TF-IDF over documenten (term -> gemiddelde tf-idf score)."""
        n_docs = len(documents)
        doc_tokens = [_content_tokens(d) for d in documents]
        df: Counter = Counter()
        for toks in doc_tokens:
            for term in set(toks):
                df[term] += 1
        scores: Dict[str, float] = defaultdict(float)
        for toks in doc_tokens:
            if not toks:
                continue
            tf = Counter(toks)
            length = len(toks)
            for term, count in tf.items():
                idf = math.log((1 + n_docs) / (1 + df[term])) + 1
                scores[term] += (count / length) * idf
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [{"term": t, "score": round(s, 4)} for t, s in ranked[:limit]]

    def _sentiment(self, text: str) -> Dict[str, float]:
        toks = _tokens(text)
        pos = sum(1 for t in toks if t in POSITIVE_WORDS)
        neg = sum(1 for t in toks if t in NEGATIVE_WORDS)
        total = pos + neg
        score = 0.0 if total == 0 else (pos - neg) / total
        if score > 0.15:
            label = "overwegend positief"
        elif score < -0.15:
            label = "overwegend negatief"
        else:
            label = "gemengd / neutraal"
        return {
            "positive_hits": float(pos),
            "negative_hits": float(neg),
            "polarity": round(score, 3),
            "label": label,
        }

    def _persona_clusters(self, documents: List[str]) -> List[Dict]:
        counts: Counter = Counter()
        examples: Dict[str, str] = {}
        for doc in documents:
            low = doc.lower()
            for persona, signals in PERSONA_SIGNALS.items():
                for sig in signals:
                    if sig in low:
                        counts[persona] += 1
                        if persona not in examples:
                            idx = low.find(sig)
                            snippet = doc[max(0, idx - 40) : idx + 80]
                            examples[persona] = truncate(snippet.strip(), 160)
                        break
        return [
            {"persona": p, "signal_count": c, "example": examples.get(p, "")}
            for p, c in counts.most_common()
        ]

    def _content_angles(self, r: AnalysisResult) -> List[str]:
        angles: List[str] = []
        for pp in r.top_pain_points[:5]:
            angles.append(f"How to solve: {pp['theme']}")
        for d in r.top_desired_outcomes[:3]:
            angles.append(f"The guide to achieving: {d['theme']}")
        for s in r.top_successful_solutions[:3]:
            angles.append(f"Why this works: {s['theme']}")
        for f in r.top_failed_solutions[:2]:
            angles.append(f"Mistakes to avoid: {f['theme']}")
        return angles[:12]

    def _ad_hooks(self, r: AnalysisResult) -> List[str]:
        hooks: List[str] = []
        for fr in r.top_frustrations[:4]:
            hooks.append(f"Tired of {fr['theme']}? Here's what actually works.")
        for pp in r.top_pain_points[:4]:
            hooks.append(f"Still struggling with {pp['theme']}? You're not alone.")
        for d in r.top_desired_outcomes[:3]:
            hooks.append(f"Finally get {d['theme']} — without the guesswork.")
        return hooks[:12]

    def _faqs(self, sentences: List[str], limit: int = 15) -> List[Dict]:
        faqs = []
        seen = set()
        for s in sentences:
            st = s.strip()
            if st.endswith("?") and 12 <= len(st) <= 200:
                key = st.lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                faqs.append({"question": truncate(st, 200)})
            if len(faqs) >= limit:
                break
        return faqs

    def _before_after(self, sentences: List[str], limit: int = 10) -> List[Dict]:
        cues = [
            r"\bused to\b.*\bnow\b", r"\bbefore\b.*\bafter\b", r"\bsince i (?:started|switched)\b",
            r"\bafter (?:a few|\d+) (?:weeks?|months?|days?)\b", r"\bever since\b",
        ]
        out = []
        for s in sentences:
            if 20 <= len(s) <= 300 and _matches_any(cues, s):
                out.append({"quote": truncate(s, 260)})
            if len(out) >= limit:
                break
        return out
