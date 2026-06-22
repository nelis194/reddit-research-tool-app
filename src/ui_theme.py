"""UI-thema voor het Streamlit-dashboard.

Designsysteem: "Data-Dense Dashboard" — blauw (#1E40AF) als datakleur met amber
(#F59E0B) accenten, Fira Sans / Fira Code typografie, subtiele kaarten en hover-
states. Eén ``inject_theme()`` zet de globale CSS; ``render_header()`` tekent een
nette kop met inline SVG-logo en status-badges.
"""

from __future__ import annotations

import html

import streamlit as st

PRIMARY = "#1E40AF"
ACCENT = "#F59E0B"
INK = "#0F172A"
MUTED = "#64748B"
BORDER = "#E2E8F0"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root { --rr-primary:#1E40AF; --rr-accent:#F59E0B; --rr-ink:#0F172A; --rr-muted:#64748B; --rr-border:#E2E8F0; }

html, body, .stApp, [class*="css"] { font-family:'Fira Sans', system-ui, -apple-system, sans-serif; }
.stApp { background:#F8FAFC; }

/* Standaard Streamlit-chrome opruimen */
[data-testid="stToolbar"], [data-testid="stDecoration"], footer { visibility:hidden; height:0; }
[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:2rem; max-width:1300px; }

/* Koppen */
h1,h2,h3,h4 { color:#1E3A8A; font-weight:700; letter-spacing:-0.01em; }

/* App-header */
.rr-header { display:flex; align-items:center; gap:16px; padding:4px 0 14px; margin-bottom:6px; border-bottom:1px solid var(--rr-border); }
.rr-logo { flex:0 0 auto; width:46px; height:46px; border-radius:12px; background:linear-gradient(135deg,#1E40AF,#3B82F6); display:flex; align-items:center; justify-content:center; box-shadow:0 4px 12px rgba(30,64,175,.25); }
.rr-title { font-size:1.55rem; font-weight:700; color:var(--rr-ink); line-height:1.1; }
.rr-sub { font-size:.9rem; color:var(--rr-muted); margin-top:2px; }
.rr-pills { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 22px; }
.rr-pill { display:inline-flex; align-items:center; gap:6px; font-size:.78rem; font-weight:500; color:#334155; background:#fff; border:1px solid var(--rr-border); border-radius:999px; padding:5px 12px; }
.rr-pill b { font-family:'Fira Code',monospace; font-weight:600; color:var(--rr-primary); }
.rr-pill .dot { width:7px; height:7px; border-radius:50%; background:var(--rr-accent); }

/* Metric-kaarten */
[data-testid="stMetric"] { background:#fff; border:1px solid var(--rr-border); border-left:4px solid var(--rr-primary); border-radius:12px; padding:14px 16px; box-shadow:0 1px 2px rgba(15,23,42,.04); }
[data-testid="stMetricValue"] { font-family:'Fira Code',monospace; color:var(--rr-primary); font-weight:600; }
[data-testid="stMetricLabel"] p { color:var(--rr-muted); font-weight:500; }

/* Tabs */
[data-baseweb="tab-list"] { gap:2px; border-bottom:1px solid var(--rr-border); }
button[data-baseweb="tab"] { font-weight:500; color:var(--rr-muted); padding:9px 16px; border-radius:8px 8px 0 0; transition:background .2s ease, color .2s ease; }
button[data-baseweb="tab"]:hover { color:var(--rr-primary); background:#EFF4FF; }
button[data-baseweb="tab"][aria-selected="true"] { color:var(--rr-primary); }
[data-baseweb="tab-highlight"] { background:var(--rr-primary); height:3px; }

/* Knoppen */
.stButton > button { border-radius:10px; font-weight:600; transition:transform .15s ease, box-shadow .2s ease, background .2s ease; }
.stButton > button:hover { transform:translateY(-1px); }
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] { background:var(--rr-primary); border:none; box-shadow:0 2px 8px rgba(30,64,175,.2); }
.stButton > button[kind="primary"]:hover { background:#1B399E; box-shadow:0 5px 16px rgba(30,64,175,.3); }
[data-testid="stSidebar"] .stButton > button { width:100%; }

/* Download-knoppen */
.stDownloadButton > button { border-radius:10px; font-weight:500; border:1px solid var(--rr-border); }

/* Inputs */
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div, [data-baseweb="input"] { border-radius:10px !important; }

/* Dataframe & expanders */
[data-testid="stDataFrame"] { border:1px solid var(--rr-border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { border:1px solid var(--rr-border); border-radius:12px; }

/* Sidebar */
[data-testid="stSidebar"] { border-right:1px solid var(--rr-border); }

/* Open-knop van de zijbalk (zichtbaar als de balk dicht is / op mobiel) */
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {
  background:var(--rr-primary); border-radius:10px; padding:3px;
  box-shadow:0 2px 10px rgba(30,64,175,.35);
}
[data-testid="stSidebarCollapsedControl"] svg, [data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] button, [data-testid="collapsedControl"] button {
  color:#fff !important; fill:#fff !important;
}
.rr-side-title { font-size:1.05rem; font-weight:700; color:var(--rr-ink); display:flex; align-items:center; gap:8px; }
.rr-side-sub { font-size:.8rem; color:var(--rr-muted); margin:2px 0 6px; }

/* Quotes / blockquotes */
blockquote { border-left:3px solid var(--rr-accent) !important; background:#FFFBEB; padding:10px 16px; border-radius:0 8px 8px 0; color:#1E293B; }

@media (prefers-reduced-motion: reduce) { * { transition:none !important; transform:none !important; } }
</style>
"""

_MAGNIFIER_SVG = (
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
)


def inject_theme() -> None:
    """Zet de globale CSS (één keer per pagina-render aanroepen)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header(pills: list) -> None:
    """Teken de app-kop met logo, titel en status-badges.

    ``pills`` is een lijst van (label, waarde)-tuples.
    """
    pill_html = "".join(
        f'<span class="rr-pill"><span class="dot"></span>{html.escape(label)} '
        f'<b>{html.escape(str(value))}</b></span>'
        for label, value in pills
    )
    st.markdown(
        f"""
        <div class="rr-header">
          <div class="rr-logo">{_MAGNIFIER_SVG}</div>
          <div>
            <div class="rr-title">Reddit Research</div>
            <div class="rr-sub">Customer- &amp; market-research uit Reddit-discussies</div>
          </div>
        </div>
        <div class="rr-pills">{pill_html}</div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, caption: str = "") -> None:
    """Consistente sectie-kop."""
    sub = f'<div class="rr-side-sub">{html.escape(caption)}</div>' if caption else ""
    st.markdown(f"#### {html.escape(title)}\n{sub}", unsafe_allow_html=True)
