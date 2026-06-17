"""Gedeelde hulpfuncties: logging, hashing, tekst- en tijd-helpers."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

_LOG_CONFIGURED = False


def setup_logging(logs_dir: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Configureer root-logging één keer (console + optioneel bestand)."""
    global _LOG_CONFIGURED
    logger = logging.getLogger("reddit_research")
    if _LOG_CONFIGURED:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    if logs_dir is not None:
        try:
            Path(logs_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                Path(logs_dir) / "reddit_research.log", encoding="utf-8"
            )
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("Kon logbestand niet aanmaken; alleen console-logging.")

    logger.propagate = False
    _LOG_CONFIGURED = True
    return logger


def get_logger(name: str = "reddit_research") -> logging.Logger:
    return logging.getLogger(name)


def now_iso() -> str:
    """Huidige UTC-tijd als ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(epoch: Optional[float]) -> Optional[str]:
    """Zet een Unix-timestamp om naar een ISO-datumstring (UTC)."""
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def stable_hash(*parts: object) -> str:
    """Deterministische hash van willekeurige onderdelen (voor deduplicatie)."""
    joined = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8", errors="ignore")).hexdigest()


def slugify(text: str, max_len: int = 60) -> str:
    """Bestandsnaam-veilige slug van een vrije tekst."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return (text or "query")[:max_len]


def normalize_keyword_list(raw: Iterable[str]) -> List[str]:
    """Splits/normaliseer een lijst keywords (komma/nieuwe regel) en dedup."""
    out: List[str] = []
    seen = set()
    for item in raw:
        if not item:
            continue
        for piece in re.split(r"[\n,;]", str(item)):
            kw = piece.strip()
            key = kw.lower()
            if kw and key not in seen:
                seen.add(key)
                out.append(kw)
    return out


def truncate(text: str, length: int = 280) -> str:
    text = (text or "").strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
