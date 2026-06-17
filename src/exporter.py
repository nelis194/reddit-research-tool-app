"""Export van data en analyse naar CSV, JSON en Markdown.

Genereert de vaste set bestanden uit de specificatie:
  raw_posts.csv, raw_comments.csv, cleaned_comments.csv,
  insights_summary.md, persona_report.md, voice_of_customer_quotes.csv,
  solution_mentions.csv, pain_points.csv, frustrations.csv,
  content_angles.csv, ad_hooks.csv
plus een volledige analysis.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .analyzer import AnalysisResult
from .parser import Comment, Post
from .utils import get_logger, now_iso, slugify

logger = get_logger()


class Exporter:
    """Schrijft exports naar een (per-run) submap onder exports/."""

    def __init__(self, exports_dir: Path, run_label: str = "run"):
        self.base_dir = Path(exports_dir)
        safe = slugify(run_label)
        self.run_dir = self.base_dir / safe
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.written: List[Path] = []

    # ------------------------------------------------------------------ ruwe data
    def export_posts(self, posts: List[Post], filename: str = "raw_posts.csv") -> Path:
        df = pd.DataFrame([p.to_dict() for p in posts])
        return self._write_csv(df, filename)

    def export_comments(self, comments: List[Comment], filename: str = "raw_comments.csv") -> Path:
        df = pd.DataFrame([c.to_dict() for c in comments])
        return self._write_csv(df, filename)

    def export_cleaned_comments(
        self, comments: List[Comment], filename: str = "cleaned_comments.csv"
    ) -> Path:
        df = pd.DataFrame([c.to_dict() for c in comments])
        return self._write_csv(df, filename)

    # ------------------------------------------------------------------ analyse
    def export_analysis_json(self, result: AnalysisResult, filename: str = "analysis.json") -> Path:
        path = self.run_dir / filename
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.written.append(path)
        return path

    def export_category_csvs(self, result: AnalysisResult) -> Dict[str, Path]:
        """Schrijf de losse categorie-CSV's uit de specificatie."""
        out: Dict[str, Path] = {}
        out["pain_points"] = self._write_csv(
            pd.DataFrame(result.top_pain_points), "pain_points.csv"
        )
        out["frustrations"] = self._write_csv(
            pd.DataFrame(result.top_frustrations), "frustrations.csv"
        )
        # solution_mentions = geslaagde + mislukte oplossingen met label.
        solutions = (
            [{**s, "type": "successful"} for s in result.top_successful_solutions]
            + [{**s, "type": "failed"} for s in result.top_failed_solutions]
        )
        out["solution_mentions"] = self._write_csv(
            pd.DataFrame(solutions), "solution_mentions.csv"
        )
        out["content_angles"] = self._write_csv(
            pd.DataFrame({"angle": result.content_angles}), "content_angles.csv"
        )
        out["ad_hooks"] = self._write_csv(
            pd.DataFrame({"hook": result.ad_hooks}), "ad_hooks.csv"
        )
        # Voice of customer plat als (categorie, quote).
        voc_rows = [
            {"category": cat, "quote": q}
            for cat, quotes in result.voice_of_customer.items()
            for q in quotes
        ]
        out["voice_of_customer"] = self._write_csv(
            pd.DataFrame(voc_rows), "voice_of_customer_quotes.csv"
        )
        return out

    # ------------------------------------------------------------------ markdown
    def export_insights_markdown(
        self, result: AnalysisResult, filename: str = "insights_summary.md"
    ) -> Path:
        lines: List[str] = []
        kw = ", ".join(result.keyword_context) or "(geen)"
        lines.append(f"# Insights Summary\n")
        lines.append(f"- **Keywords/onderwerp:** {kw}")
        lines.append(f"- **Geanalyseerde documenten:** {result.document_count}")
        lines.append(f"- **Gegenereerd:** {now_iso()}")
        if result.sentiment:
            lines.append(
                f"- **Sentiment:** {result.sentiment.get('label')} "
                f"(polariteit {result.sentiment.get('polarity')})"
            )
        lines.append("")
        if result.is_medical and result.disclaimer:
            lines.append(f"> {result.disclaimer}\n")

        lines += self._md_theme_section("Top pijnpunten", result.top_pain_points)
        lines += self._md_theme_section("Top frustraties", result.top_frustrations)
        lines += self._md_theme_section("Gewenste uitkomsten", result.top_desired_outcomes)
        lines += self._md_theme_section("Geslaagde oplossingen", result.top_successful_solutions)
        lines += self._md_theme_section("Mislukte oplossingen", result.top_failed_solutions)
        lines += self._md_theme_section("Koopbezwaren", result.buying_objections)
        lines += self._md_theme_section("Koopmotieven", result.buying_motivations)

        if result.mentioned_brands:
            lines.append("## Genoemde merken/producten\n")
            for b in result.mentioned_brands[:20]:
                lines.append(f"- {b['term']} ({b['count']}x)")
            lines.append("")

        if result.common_phrases:
            lines.append("## Veelgebruikte zinnen\n")
            for p in result.common_phrases[:20]:
                lines.append(f"- \"{p['phrase']}\" ({p['count']}x)")
            lines.append("")

        if result.content_angles:
            lines.append("## Content angles\n")
            for a in result.content_angles:
                lines.append(f"- {a}")
            lines.append("")

        if result.ad_hooks:
            lines.append("## Ad hooks\n")
            for h in result.ad_hooks:
                lines.append(f"- {h}")
            lines.append("")

        if result.faqs:
            lines.append("## FAQ's (uit echte vragen)\n")
            for f in result.faqs:
                lines.append(f"- {f['question']}")
            lines.append("")

        self._append_llm_markdown(lines, result.llm_insights)

        return self._write_text("\n".join(lines), filename)

    def export_persona_markdown(
        self, result: AnalysisResult, filename: str = "persona_report.md"
    ) -> Path:
        lines: List[str] = ["# Persona Report\n"]
        kw = ", ".join(result.keyword_context) or "(geen)"
        lines.append(f"- **Onderwerp:** {kw}")
        lines.append(f"- **Gegenereerd:** {now_iso()}\n")

        if result.persona_clusters:
            lines.append("## Persona-clusters (op basis van taalgebruik)\n")
            lines.append(
                "_Persona's zijn afgeleid uit taalgebruik en inhoud, niet uit gebruikersaccounts._\n"
            )
            for p in result.persona_clusters:
                lines.append(f"### {p['persona'].title()} ({p['signal_count']} signalen)")
                if p.get("example"):
                    lines.append(f"> {p['example']}")
                lines.append("")
        else:
            lines.append("_Geen duidelijke persona-signalen gevonden._\n")

        # LLM persona cards (indien aanwezig).
        cards = (result.llm_insights or {}).get("persona_cards") if result.llm_insights else None
        if cards:
            lines.append("## Persona cards (LLM)\n")
            for card in cards:
                lines.append(f"### {card.get('name', 'Persona')}")
                if card.get("description"):
                    lines.append(card["description"])
                for key, title in [
                    ("pains", "Pijnpunten"),
                    ("desires", "Verlangens"),
                    ("objections", "Bezwaren"),
                    ("language", "Taalgebruik"),
                ]:
                    items = card.get(key) or []
                    if items:
                        lines.append(f"- **{title}:** " + "; ".join(map(str, items)))
                lines.append("")

        return self._write_text("\n".join(lines), filename)

    def export_all(
        self,
        result: AnalysisResult,
        posts: List[Post],
        raw_comments: List[Comment],
        cleaned_comments: List[Comment],
    ) -> List[Path]:
        """Schrijf de complete export-set en geef de paden terug."""
        self.export_posts(posts)
        self.export_comments(raw_comments)
        self.export_cleaned_comments(cleaned_comments)
        self.export_analysis_json(result)
        self.export_category_csvs(result)
        self.export_insights_markdown(result)
        self.export_persona_markdown(result)
        logger.info("Export klaar: %d bestanden in %s", len(self.written), self.run_dir)
        return self.written

    # ------------------------------------------------------------------ interne
    @staticmethod
    def _md_theme_section(title: str, items: List[Dict]) -> List[str]:
        if not items:
            return []
        out = [f"## {title}\n"]
        for it in items[:12]:
            theme = it.get("theme", "")
            count = it.get("count", "")
            example = it.get("example", "")
            out.append(f"- **{theme}** ({count}x)")
            if example:
                out.append(f"  - _\"{example}\"_")
        out.append("")
        return out

    @staticmethod
    def _append_llm_markdown(lines: List[str], llm: Optional[Dict]) -> None:
        if not llm:
            return
        lines.append("## LLM-inzichten\n")
        for key, title in [
            ("thematic_summaries", "Thematische samenvattingen"),
            ("marketing_insights", "Marketing insights"),
            ("customer_insights", "Customer insights"),
            ("content_ideas", "Content-ideeën"),
            ("landing_page_hooks", "Landing page hooks"),
            ("offer_ideas", "Offer-ideeën"),
        ]:
            items = llm.get(key) or []
            if items:
                lines.append(f"### {title}")
                for it in items:
                    lines.append(f"- {it}")
                lines.append("")

    def _write_csv(self, df: pd.DataFrame, filename: str) -> Path:
        path = self.run_dir / filename
        if df.empty:
            # Schrijf nog steeds een (lege) header-loze placeholder voor consistentie.
            df = pd.DataFrame()
        df.to_csv(path, index=False)
        self.written.append(path)
        return path

    def _write_text(self, text: str, filename: str) -> Path:
        path = self.run_dir / filename
        path.write_text(text, encoding="utf-8")
        self.written.append(path)
        return path
