"""Streamlit-dashboard voor de Reddit Research Tool.

Start met:  streamlit run app.py

Flow: keywords/subreddits invoeren -> scrapen -> analyseren -> filteren ->
inzichten bekijken (pijnpunten, frustraties, oplossingen, quotes, persona's) ->
exporteren naar CSV/JSON/Markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

# Zorg dat 'src' importeerbaar is, ook als gestart vanuit een andere cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.analyzer import Analyzer, AnalysisResult  # noqa: E402
from src.cleaner import clean_comments, clean_posts  # noqa: E402
from src.config import load_config  # noqa: E402
from src.database import Database  # noqa: E402
from src.exporter import Exporter  # noqa: E402
from src.llm_analyzer import LLMAnalyzer  # noqa: E402
from src.parser import Comment, Post  # noqa: E402
from src.scraper import RedditScraper  # noqa: E402
from src.ui_theme import inject_theme, render_header  # noqa: E402
from src.utils import normalize_keyword_list, setup_logging, slugify  # noqa: E402

st.set_page_config(
    page_title="Reddit Research", page_icon="🔎", layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()


@st.cache_resource
def get_config():
    cfg = load_config()
    setup_logging(cfg.logs_dir)
    return cfg


CONFIG = get_config()


# --------------------------------------------------------------------- helpers
def _init_state() -> None:
    defaults = {
        "posts": [],
        "raw_comments": [],
        "cleaned_comments": [],
        "analysis": None,
        "search_label": "",
        "scraped": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _documents_from_state() -> List[str]:
    docs = []
    for p in st.session_state["posts"]:
        text = f"{p.title}\n{p.selftext}".strip()
        if text:
            docs.append(text)
    for c in st.session_state["cleaned_comments"]:
        if c.body:
            docs.append(c.body)
    return docs


def _comments_dataframe() -> pd.DataFrame:
    rows = [c.to_dict() for c in st.session_state["cleaned_comments"]]
    return pd.DataFrame(rows)


def _posts_dataframe() -> pd.DataFrame:
    rows = [p.to_dict() for p in st.session_state["posts"]]
    return pd.DataFrame(rows)


_init_state()

# ------------------------------------------------------------------- sidebar
st.sidebar.markdown(
    '<div class="rr-side-title">Zoekopdracht</div>'
    '<div class="rr-side-sub">Vul één of meer keywords in en start de research.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    keywords_raw = st.text_area(
        "Keywords / onderwerpen / concurrenten",
        placeholder='"cocoa" AND "blood pressure"\n"dark chocolate" AND "heart health"\n"epicatechin" AND "cacao"',
        help=(
            "Eén zoekopdracht per regel. Reddit-operatoren werken (laat hiervoor het "
            "subreddit-veld leeg): rechte aanhalingstekens \" \" voor exacte zinnen, "
            "AND / OR / NOT (hoofdletters) om te combineren. Gebruik géén komma's binnen "
            "een zoekopdracht — die splitsen 'm op."
        ),
        height=140,
    )
    subreddits_raw = st.text_input(
        "Subreddits (optioneel)",
        placeholder="skincareaddiction, supplements",
        help="Leeg = heel Reddit. Anders komma-gescheiden subreddits.",
    )
    competitor_raw = st.text_input(
        "Concurrent-termen (optioneel)",
        placeholder="brand A, brand B",
        help="Worden geteld als 'mentioned competitors'.",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        sort = st.selectbox(
            "Sortering", ["relevance", "hot", "top", "new", "comments"], index=0
        )
    with col_b:
        time_filter = st.selectbox(
            "Periode", ["all", "day", "week", "month", "year"], index=0
        )

    max_posts = st.slider("Max posts per zoekterm", 10, 500, min(100, CONFIG.max_posts_per_query), 10)
    max_comments = st.slider("Max comments per post", 0, 500, min(100, CONFIG.max_comments_per_post), 10)
    target_lang = st.selectbox(
        "Taalfilter", ["(geen)", "en", "nl", "de", "fr", "es"], index=0
    )

    st.divider()
    if CONFIG.dry_run:
        st.warning("DRY_RUN actief — geen echte HTTP-verzoeken.")

    scrape_clicked = st.button("Scrape starten", type="primary", use_container_width=True)
    analyze_clicked = st.button("Analyseren", use_container_width=True)
    load_clicked = st.button(
        "Laad opgeslagen scrape",
        use_container_width=True,
        help="Haal je laatste scrape uit Supabase — handig om opnieuw te analyseren zonder opnieuw te scrapen.",
    )


# --------------------------------------------------------------------- scrape
def run_scrape() -> None:
    keywords = normalize_keyword_list([keywords_raw])
    if not keywords:
        st.error("Voer minstens één keyword/onderwerp in.")
        return
    subreddits = normalize_keyword_list([subreddits_raw]) if subreddits_raw else []
    lang = None if target_lang == "(geen)" else target_lang

    progress_bar = st.progress(0.0, text="Starten…")
    status = st.empty()

    def on_progress(phase: str, current: int, total: int, message: str) -> None:
        frac = current / total if total else 0.0
        progress_bar.progress(min(1.0, frac), text=message)
        status.info(message)

    scraper = RedditScraper(CONFIG)
    try:
        result = scraper.scrape(
            keywords=keywords,
            subreddits=subreddits,
            sort=sort,
            time_filter=time_filter,
            max_posts_per_query=max_posts,
            max_comments_per_post=max_comments,
            fetch_comments=max_comments > 0,
            progress=on_progress,
        )
    finally:
        scraper.close()

    # Opschonen.
    posts = clean_posts(result.posts, target_language=lang)
    cleaned = clean_comments(result.comments, target_language=lang)

    st.session_state["posts"] = posts
    st.session_state["raw_comments"] = result.comments
    st.session_state["cleaned_comments"] = cleaned
    st.session_state["search_label"] = " ".join(keywords[:3])
    st.session_state["scraped"] = True
    st.session_state["analysis"] = None

    # Persistente opslag.
    try:
        db = Database(CONFIG)
        db.init_db()
        sid = db.save_search(keywords, subreddits, sort, time_filter, len(posts), len(cleaned))
        db.save_posts(posts, sid)
        db.save_comments(cleaned, sid)
        db.close()
    except Exception as exc:  # database mag de UI niet breken
        st.warning(f"Opslaan in database overgeslagen: {exc}")

    progress_bar.progress(1.0, text="Klaar")
    status.success(
        f"Verzameld: {len(posts)} posts en {len(cleaned)} comments "
        f"(na opschonen) voor {len(keywords)} zoekterm(en)."
    )


def run_analysis() -> None:
    docs = _documents_from_state()
    if not docs:
        st.error("Geen data om te analyseren. Scrape eerst.")
        return
    competitors = normalize_keyword_list([competitor_raw]) if competitor_raw else []
    keywords = normalize_keyword_list([keywords_raw])
    subreddits = [p.subreddit for p in st.session_state["posts"]] + [
        c.subreddit for c in st.session_state["cleaned_comments"]
    ]

    with st.spinner("Lokale analyse uitvoeren…"):
        analyzer = Analyzer(keyword_context=keywords)
        result = analyzer.analyze(docs, subreddits=subreddits, competitor_terms=competitors)

    if CONFIG.llm_enabled:
        with st.spinner("LLM-verrijking (OpenAI)…"):
            quotes = [q for qs in result.voice_of_customer.values() for q in qs]
            llm = LLMAnalyzer(CONFIG).enrich(result, sample_quotes=quotes)
            if llm:
                result.llm_insights = llm

    st.session_state["analysis"] = result

    try:
        db = Database(CONFIG)
        db.init_db()
        db.save_analysis(None, "full", result.to_dict())
        db.close()
    except Exception as exc:
        st.warning(f"Analyse opslaan overgeslagen: {exc}")

    st.success("Analyse klaar. Bekijk de tabbladen hieronder.")


def _post_from_row(r: dict) -> Post:
    return Post(
        post_id=r.get("post_id"), subreddit=r.get("subreddit"),
        title=r.get("title") or "", selftext=r.get("selftext") or "",
        url=r.get("url"), score=r.get("score") or 0,
        num_comments=r.get("num_comments") or 0, created_date=r.get("created_date"),
        permalink=r.get("permalink"), keyword=r.get("keyword"),
        flair=r.get("flair"), source_url=r.get("source_url"),
    )


def _comment_from_row(r: dict) -> Comment:
    return Comment(
        comment_id=r.get("comment_id"), post_id=r.get("post_id"),
        parent_id=r.get("parent_id"), body=r.get("body") or "",
        score=r.get("score") or 0, created_date=r.get("created_date"),
        depth=r.get("depth") or 0, permalink=r.get("permalink"),
        keyword=r.get("keyword"), subreddit=r.get("subreddit"),
        source_url=r.get("source_url"),
    )


def load_from_db() -> None:
    """Haal de laatste opgeslagen scrape uit de database in session_state."""
    try:
        db = Database(CONFIG)
        db.init_db()
        sid = db.latest_search_id()
        if not sid:
            st.warning("Geen opgeslagen scrape gevonden in de database.")
            db.close()
            return
        prows = db.fetch_posts(sid)
        crows = db.fetch_comments(sid)
        db.close()
    except Exception as exc:
        st.error(f"Laden uit database mislukt: {exc}")
        return

    posts = [_post_from_row(r) for r in prows]
    comments = [_comment_from_row(r) for r in crows]
    st.session_state["posts"] = posts
    st.session_state["raw_comments"] = comments
    st.session_state["cleaned_comments"] = comments  # waren al opgeschoond bij opslaan
    st.session_state["analysis"] = None
    st.session_state["scraped"] = True
    st.success(
        f"Geladen uit Supabase: {len(posts)} posts en {len(comments)} comments. "
        "Klik nu op **Analyseren**."
    )


if scrape_clicked:
    run_scrape()
if analyze_clicked:
    run_analysis()
if load_clicked:
    load_from_db()


# --------------------------------------------------------------------- main UI
render_header(
    [
        ("Bron", CONFIG.data_source_label),
        ("LLM", CONFIG.active_llm_label),
        ("Database", "Supabase" if CONFIG.uses_postgres else "SQLite"),
    ]
)

analysis: AnalysisResult = st.session_state.get("analysis")

if analysis and analysis.is_medical and analysis.disclaimer:
    st.warning(analysis.disclaimer)

# Statusbalk.
c1, c2, c3, c4 = st.columns(4)
c1.metric("Posts", len(st.session_state["posts"]))
c2.metric("Comments (schoon)", len(st.session_state["cleaned_comments"]))
c3.metric("Subreddits", len({p.subreddit for p in st.session_state["posts"]}))
c4.metric("Analyse", "Klaar" if analysis else "—")

tabs = st.tabs(
    [
        "Resultaten",
        "Pijnpunten",
        "Frustraties",
        "Oplossingen",
        "Quotes",
        "Persona's",
        "Inzichten",
        "Export",
    ]
)

# --- Tab: resultaten met filters ---
with tabs[0]:
    df = _comments_dataframe()
    pdf = _posts_dataframe()
    st.subheader("Posts")
    if not pdf.empty:
        fcol1, fcol2, fcol3 = st.columns(3)
        subs = sorted([s for s in pdf["subreddit"].dropna().unique()])
        kws = sorted([k for k in pdf["keyword"].dropna().unique()])
        with fcol1:
            sub_sel = st.multiselect("Subreddit", subs, key="psub")
        with fcol2:
            kw_sel = st.multiselect("Keyword", kws, key="pkw")
        with fcol3:
            min_score = st.number_input("Min. score", value=0, step=1, key="pscore")
        view = pdf.copy()
        if sub_sel:
            view = view[view["subreddit"].isin(sub_sel)]
        if kw_sel:
            view = view[view["keyword"].isin(kw_sel)]
        view = view[view["score"].fillna(0) >= min_score]
        st.caption(f"{len(view)} posts")
        st.dataframe(view, use_container_width=True, height=320)
    else:
        st.info("Nog geen posts. Gebruik **Scrape** in de zijbalk.")

    st.subheader("Comments")
    if not df.empty:
        gcol1, gcol2 = st.columns(2)
        with gcol1:
            csub = st.multiselect(
                "Subreddit", sorted([s for s in df["subreddit"].dropna().unique()]), key="csub"
            )
        with gcol2:
            cmin = st.number_input("Min. score", value=0, step=1, key="cscore")
        cview = df.copy()
        if csub:
            cview = cview[cview["subreddit"].isin(csub)]
        cview = cview[cview["score"].fillna(0) >= cmin]
        st.caption(f"{len(cview)} comments")
        st.dataframe(
            cview[["subreddit", "keyword", "score", "depth", "body"]],
            use_container_width=True,
            height=320,
        )
    else:
        st.info("Nog geen comments.")


def _theme_table(title: str, items, key: str):
    st.subheader(title)
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, height=360)
    else:
        st.info("Geen resultaten — voer eerst een analyse uit.")


with tabs[1]:
    _theme_table("Top pijnpunten", analysis.top_pain_points if analysis else [], "pp")
    if analysis:
        _theme_table("Terugkerende klachten", analysis.recurring_complaints, "rc")

with tabs[2]:
    _theme_table("Top frustraties", analysis.top_frustrations if analysis else [], "fr")

with tabs[3]:
    if analysis:
        _theme_table("Geslaagde oplossingen", analysis.top_successful_solutions, "ss")
        _theme_table("Mislukte oplossingen", analysis.top_failed_solutions, "fs")
        _theme_table("Gewenste uitkomsten", analysis.top_desired_outcomes, "do")
        _theme_table("Genoemde merken/producten", analysis.mentioned_brands, "mb")
        _theme_table("Genoemde concurrenten", analysis.mentioned_competitors, "mc")
    else:
        st.info("Voer eerst een analyse uit.")

with tabs[4]:
    st.subheader("Voice of Customer")
    if analysis and analysis.voice_of_customer:
        for cat, quotes in analysis.voice_of_customer.items():
            if quotes:
                with st.expander(f"{cat.replace('_', ' ').title()} ({len(quotes)})", expanded=False):
                    for q in quotes:
                        st.markdown(f"> {q}")
    else:
        st.info("Geen quotes — voer eerst een analyse uit.")

with tabs[5]:
    st.subheader("Persona-clusters")
    st.caption("Afgeleid uit taalgebruik en inhoud, niet uit gebruikersaccounts.")
    if analysis and analysis.persona_clusters:
        st.dataframe(pd.DataFrame(analysis.persona_clusters), use_container_width=True)
        cards = (analysis.llm_insights or {}).get("persona_cards") if analysis.llm_insights else None
        if cards:
            st.subheader("Persona cards (LLM)")
            for card in cards:
                with st.expander(card.get("name", "Persona")):
                    st.write(card.get("description", ""))
                    st.json(card)
    else:
        st.info("Geen persona-signalen — voer eerst een analyse uit.")

with tabs[6]:
    if analysis:
        icol1, icol2 = st.columns(2)
        with icol1:
            _theme_table("Koopmotieven", analysis.buying_motivations, "bm")
            st.subheader("Content angles")
            for a in analysis.content_angles:
                st.markdown(f"- {a}")
            st.subheader("Veelgebruikte zinnen")
            st.dataframe(pd.DataFrame(analysis.common_phrases), use_container_width=True, height=240)
        with icol2:
            _theme_table("Koopbezwaren", analysis.buying_objections, "bo")
            st.subheader("Ad hooks")
            for h in analysis.ad_hooks:
                st.markdown(f"- {h}")
            st.subheader("Sentiment")
            st.json(analysis.sentiment)
        st.subheader("FAQ's (uit echte vragen)")
        st.dataframe(pd.DataFrame(analysis.faqs), use_container_width=True, height=240)
        if analysis.llm_insights:
            st.subheader("LLM-inzichten")
            st.json(analysis.llm_insights)
    else:
        st.info("Voer eerst een analyse uit.")

with tabs[7]:
    st.subheader("Exporteren")
    if not analysis:
        st.info("Voer eerst een analyse uit om alle exports te genereren.")
    else:
        # Word-rapport: alle hoofdstukken in één net document.
        st.markdown("**Word-rapport** — alle hoofdstukken (pijnpunten, frustraties, "
                    "oplossingen, quotes, persona's, inzichten) in één net document.")
        try:
            from src.docx_report import build_docx

            docx_bytes = build_docx(
                analysis,
                posts_count=len(st.session_state["posts"]),
                comments_count=len(st.session_state["cleaned_comments"]),
            )
            label = st.session_state.get("search_label") or "reddit-research"
            st.download_button(
                "Download Word-rapport (.docx)",
                data=docx_bytes,
                file_name=f"reddit-research-{slugify(label)}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Word-rapport genereren mislukt: {exc}")

        st.divider()
        st.markdown("**Losse bestanden** (CSV / JSON / Markdown):")
        if st.button("Genereer alle exports"):
            label = st.session_state.get("search_label") or "run"
            exporter = Exporter(CONFIG.exports_dir, run_label=label)
            paths = exporter.export_all(
                analysis,
                st.session_state["posts"],
                st.session_state["raw_comments"],
                st.session_state["cleaned_comments"],
            )
            st.success(f"{len(paths)} bestanden geschreven naar `{exporter.run_dir}`")
            for p in paths:
                try:
                    data = Path(p).read_bytes()
                    st.download_button(
                        f"Download {Path(p).name}", data=data, file_name=Path(p).name, key=str(p)
                    )
                except OSError:
                    st.write(str(p))
