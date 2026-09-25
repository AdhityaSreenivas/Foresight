"""
PSIF Platform — Text Preprocessing

Combines and cleans free-text incident fields into the composite_narrative
that is fed to the BERT encoder.

Design decisions:
  - We keep original casing because distilbert-base-uncased handles
    case normalization internally.
  - HTML/markup stripping is minimal (strip tags, normalize whitespace).
    We do NOT apply heavy NLP preprocessing (stop-word removal, stemming)
    because BERT's subword tokenizer benefits from natural language text.
  - Fields are combined in order: description → corrective_actions →
    witness_statement, separated by " [SEP] " so the model can implicitly
    learn field boundaries.
  - BERT has a hard input limit of 512 tokens for distilbert-base-uncased.
    We truncate at the tokenizer level (handled in bert_encoder.py), not
    here — truncation here would be character-level, not token-level.
    FUTURE: a sliding-window or extractive-summarization approach would
    preserve more content from very long narratives.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Separator inserted between different narrative fields in the composite text.
FIELD_SEPARATOR = " [SEP] "


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace(
        "&gt;", ">").replace("&nbsp;", " ").replace("&quot;", '"')
    return clean


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace (spaces, tabs, newlines) to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def clean_text_field(text: Optional[str]) -> str:
    """
    Clean a single free-text field:
      1. Strip HTML tags and decode common entities
      2. Normalize whitespace
      3. Return empty string if input is None/empty
    """
    if not text:
        return ""
    text = _strip_html(str(text))
    text = _normalize_whitespace(text)
    return text


def build_composite_narrative(
    description: Optional[str] = None,
    corrective_actions: Optional[str] = None,
    witness_statement: Optional[str] = None,
) -> str:
    """
    Combine and clean the three free-text incident fields into a single string
    that will be tokenized and encoded by BERT.

    Field order (fixed, must not change at inference time):
        description → corrective_actions → witness_statement

    Empty/missing fields are omitted from the concatenation.

    Args:
        description:        Main incident narrative.
        corrective_actions: Corrective / preventive actions taken or planned.
        witness_statement:  Witness account(s).

    Returns:
        Cleaned composite narrative string (may be empty if all fields are None).

    Note on truncation:
        distilbert-base-uncased supports up to 512 tokens.  Very long
        composite narratives will be truncated at the tokenizer level in
        bert_encoder.py.  This function does NOT truncate — it is the
        tokenizer's job to do so consistently with the model's training.
        A sliding-window approach is a documented future improvement.
    """
    parts = []
    for field in (description, corrective_actions, witness_statement):
        cleaned = clean_text_field(field)
        if cleaned:
            parts.append(cleaned)

    composite = FIELD_SEPARATOR.join(parts)

    if not composite:
        logger.debug("build_composite_narrative: all text fields empty/None — returning empty string")

    return composite


def is_sparse_narrative(text: Optional[str], min_words: int = 10) -> bool:
    """
    Determine if an incident narrative contains insufficient evidence based on word count.

    Canonical rule across model inference, dataset backfill, dashboard, decision trace, and UI:
      < 10 words = sparse / insufficient evidence.
      >= 10 words = non-sparse / eligible for evaluation.

    Guarantees:
      - None or empty string -> True (sparse)
      - Whitespace-only -> True (sparse)
      - Punctuation-only -> True (sparse)
      - 9 words -> True (sparse)
      - 10 words -> False (not sparse)
      - 11 words -> False (not sparse)
    """
    if not text:
        return True

    cleaned = str(text).strip()
    if not cleaned:
        return True

    # Count tokens that contain at least one alphanumeric character (handles punctuation-only strings)
    words = [w for w in cleaned.split() if any(c.isalnum() for c in w)]
    return len(words) < min_words
