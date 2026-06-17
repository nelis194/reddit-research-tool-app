"""Optionele LLM-verrijking via Claude (Anthropic) of OpenAI.

Standaard gebruikt deze module **Claude** (Anthropic). Zet ``LLM_PROVIDER=openai``
om OpenAI te gebruiken. Als er geen geldige key/provider is (of de SDK ontbreekt,
of de API faalt) geeft ``enrich`` ``None`` terug en blijft de aanroeper leunen op
de lokale analyse.

Gegenereerde inzichten: thematische samenvattingen, persona cards/clusters,
marketing- & customer-insights, content-ideeën, ad hooks, FAQ's (met antwoord),
landing page hooks en offer-ideeën.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from .analyzer import AnalysisResult
from .config import Config
from .utils import get_logger, truncate

logger = get_logger()


SYSTEM_PROMPT = (
    "You are a senior customer & market research analyst. You receive raw, "
    "anonymized Reddit discussion content and a pre-computed local analysis. "
    "Return ONLY valid JSON matching the requested schema — no prose, no markdown "
    "fences. Be concrete, quote real customer language, and never invent usernames "
    "or personal data. If the topic is health/medical, treat all claims as "
    "user-reported and anecdotal and add a disclaimer."
)

# Gewenste JSON-structuur (ook bruikbaar als documentatie/contract).
OUTPUT_SCHEMA_HINT = {
    "thematic_summaries": ["string"],
    "persona_cards": [
        {
            "name": "string",
            "description": "string",
            "pains": ["string"],
            "desires": ["string"],
            "objections": ["string"],
            "language": ["string"],
        }
    ],
    "persona_clusters": ["string"],
    "marketing_insights": ["string"],
    "customer_insights": ["string"],
    "content_ideas": ["string"],
    "ad_hooks": ["string"],
    "faqs": [{"question": "string", "answer": "string"}],
    "landing_page_hooks": ["string"],
    "offer_ideas": ["string"],
}


class LLMAnalyzer:
    """Provider-onafhankelijke wrapper rond Claude / OpenAI."""

    def __init__(self, config: Config):
        self.config = config
        self.provider = config.llm_provider
        self._client = None

    @property
    def available(self) -> bool:
        return self.config.llm_enabled

    def enrich(
        self,
        local: AnalysisResult,
        sample_quotes: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """Genereer rijke inzichten. Geeft None bij ontbrekende key of fout."""
        if not self.available:
            logger.info("Geen LLM-key voor provider '%s'; verrijking overgeslagen.", self.provider)
            return None

        prompt = self._build_prompt(local, sample_quotes or [])
        try:
            if self.provider == "openai":
                content = self._call_openai(prompt)
            else:
                content = self._call_anthropic(prompt)
            if content is None:
                return None
            data = self._parse_json(content)
            logger.info("LLM-verrijking geslaagd (%s).", self.config.active_llm_label)
            return data
        except Exception as exc:  # netwerk, rate limit, parse, etc.
            logger.warning("LLM-verrijking mislukt (%s): %s", self.provider, exc)
            return None

    # ----------------------------------------------------------- providers
    def _call_anthropic(self, prompt: str) -> Optional[str]:
        try:
            import anthropic  # type: ignore
        except ImportError:
            logger.warning("anthropic-package niet geïnstalleerd; LLM-analyse overgeslagen.")
            return None
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        # Adaptive thinking voor een grondige analyse; ruime max_tokens.
        resp = self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )

    def _call_openai(self, prompt: str) -> Optional[str]:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            logger.warning("openai-package niet geïnstalleerd; LLM-analyse overgeslagen.")
            return None
        if self._client is None:
            self._client = OpenAI(api_key=self.config.openai_api_key)
        resp = self._client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _parse_json(content: str) -> Dict:
        """Parse JSON, ook als het model per ongeluk ```json-fences toevoegt."""
        text = content.strip()
        if text.startswith("```"):
            # Strip ``` of ```json … ``` fences.
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text[: -3]
            text = text.strip()
        return json.loads(text)

    def _build_prompt(self, local: AnalysisResult, sample_quotes: List[str]) -> str:
        context = {
            "keywords": local.keyword_context,
            "is_medical": local.is_medical,
            "document_count": local.document_count,
            "top_pain_points": [p.get("theme") for p in local.top_pain_points[:10]],
            "top_frustrations": [p.get("theme") for p in local.top_frustrations[:10]],
            "top_desired_outcomes": [p.get("theme") for p in local.top_desired_outcomes[:10]],
            "failed_solutions": [p.get("theme") for p in local.top_failed_solutions[:8]],
            "successful_solutions": [p.get("theme") for p in local.top_successful_solutions[:8]],
            "buying_objections": [p.get("theme") for p in local.buying_objections[:8]],
            "buying_motivations": [p.get("theme") for p in local.buying_motivations[:8]],
            "mentioned_brands": [b.get("term") for b in local.mentioned_brands[:15]],
            "common_phrases": [p.get("phrase") for p in local.common_phrases[:20]],
            "sentiment": local.sentiment,
        }
        quotes = [truncate(q, 240) for q in sample_quotes[:40]]
        medical_note = (
            "\nIMPORTANT: This is a health/medical topic. Label every claim as "
            "user-reported and anecdotal; add a disclaimer; do not give medical advice."
            if local.is_medical
            else ""
        )
        return (
            "Analyze the following Reddit research context and customer quotes. "
            "Produce marketing & customer-research insights.\n\n"
            f"LOCAL_ANALYSIS:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            f"SAMPLE_QUOTES (anonymized):\n{json.dumps(quotes, ensure_ascii=False, indent=2)}\n\n"
            f"Return JSON with EXACTLY these keys:\n"
            f"{json.dumps(OUTPUT_SCHEMA_HINT, ensure_ascii=False, indent=2)}"
            f"{medical_note}"
        )
