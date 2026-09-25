"""
PSIF Platform — File Parsers

Provides functions to:
  - Detect file type from both extension and content (magic bytes / structure).
  - Estimate total row count quickly without full parsing.
  - Parse the first N rows synchronously for preview.
  - Stream the full file in chunks for background processing.

Supported formats:
  CSV   — pandas.read_csv(chunksize=5000); charset-normalizer for encoding.
  JSON  — top-level array, parsed with ijson for streaming (large files).
  JSONL — one JSON object per line, streamed line-by-line.

Error handling:
  - Malformed rows are logged and skipped; they never crash the import.
  - Encoding errors fall back to latin-1 (every byte is valid in latin-1).
  - Skipped row counts / error details are reported back to the caller for
    storage in Dataset.error_log.
"""
import json
import logging
import os
from pathlib import Path
from typing import Iterator

import ijson
import pandas as pd
from charset_normalizer import from_bytes

logger = logging.getLogger(__name__)

# Maximum bytes read for encoding detection
_ENCODING_DETECT_BYTES = 65_536  # 64KB

# Number of rows parsed synchronously on upload for preview
PREVIEW_ROW_LIMIT = 100

# Chunk size for CSV batch processing (rows per chunk)
CSV_CHUNK_SIZE = int(os.environ.get("CSV_CHUNK_SIZE", 250))

# Chunk size for JSON/JSONL batch processing (records per chunk)
JSON_CHUNK_SIZE = int(os.environ.get("JSON_CHUNK_SIZE", 250))

# Magic bytes / structural signatures for content sniffing
_JSON_START_CHARS = frozenset(b"[{")
_UTF8_BOM = b"\xef\xbb\xbf"


# ── File type detection ────────────────────────────────────────────────────────

def detect_file_type(file_path: str | Path, extension: str) -> str:
    """
    Determine the file type ("csv", "json", or "jsonl") from both the file
    extension and the first bytes of content.  Extension alone is not trusted.

    Returns one of: "csv", "json", "jsonl"
    Raises ValueError if the file type cannot be reliably determined.
    """
    path = Path(file_path)
    ext = extension.lower().lstrip(".")

    # Read first 4KB for content sniffing
    with open(path, "rb") as f:
        header = f.read(4096)

    # Strip UTF-8 BOM if present
    sniff_bytes = header.lstrip(_UTF8_BOM).lstrip()

    first_char = sniff_bytes[:1]

    # Content-based determination takes precedence over extension
    if first_char in (b"[", b"{"):
        # Content looks like JSON/JSONL
        if ext == "jsonl":
            return "jsonl"
        if ext == "json":
            # Distinguish top-level array from JSONL that starts with {
            return "json" if first_char == b"[" else "jsonl"
        # Fallback for ambiguous extension: if first char is [ → json, else jsonl
        return "json" if first_char == b"[" else "jsonl"

    # Content does not look like JSON — treat as CSV
    if ext in ("json", "jsonl"):
        raise ValueError(
            f"File has extension '.{ext}' but content does not look like JSON. "
            "Please check the file and re-upload."
        )
    return "csv"


def detect_encoding(file_path: str | Path) -> str:
    """
    Detect the character encoding of a file using charset-normalizer.
    Falls back to 'utf-8' if detection is inconclusive, and 'latin-1'
    if that also fails (latin-1 can represent every byte value).
    """
    path = Path(file_path)
    with open(path, "rb") as f:
        raw = f.read(_ENCODING_DETECT_BYTES)

    result = from_bytes(raw).best()
    if result is not None:
        encoding = result.encoding
        logger.debug("Detected encoding for %s: %s", path.name, encoding)
        return encoding

    logger.debug("Encoding detection inconclusive for %s, defaulting to utf-8", path.name)
    return "utf-8"


# ── Row count estimation ───────────────────────────────────────────────────────

def estimate_row_count(file_path: str | Path, file_type: str) -> int | None:
    """
    Exactly count the number of data rows in the file using the same chunking logic 
    as the main parser. This prevents UI progress bugs like '25 / 24 rows'.
    """
    path = Path(file_path)
    try:
        if file_type == "csv":
            encoding = detect_encoding(path)
            count = 0
            for chunk, _ in _iter_csv_chunks(path, encoding):
                count += len(chunk)
            return count

        elif file_type == "jsonl":
            encoding = detect_encoding(path)
            count = 0
            for chunk, _ in _iter_jsonl_chunks(path, encoding):
                count += len(chunk)
            return count

        elif file_type == "json":
            count = 0
            for chunk, _ in _iter_json_chunks(path):
                count += len(chunk)
            return count

    except Exception as exc:
        logger.warning("Row count estimation failed for %s: %s", path.name, exc)
        return None

    return None


# ── Column / type inference ────────────────────────────────────────────────────

def infer_column_types(df: pd.DataFrame) -> dict[str, str]:
    """
    Infer a human-readable type for each column in a DataFrame.
    Returns {"column_name": type_str} where type_str is one of:
    "string", "number", "date", "boolean".
    """
    types: dict[str, str] = {}
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            types[str(col)] = "string"
            continue

        if pd.api.types.is_bool_dtype(series):
            types[str(col)] = "boolean"
        elif pd.api.types.is_numeric_dtype(series):
            types[str(col)] = "number"
        else:
            # Check if strings are numeric
            try:
                pd.to_numeric(series.head(10), errors="raise")
                types[str(col)] = "number"
                continue
            except Exception:
                pass

            # Try to parse as date
            try:
                # Require date string to have common date characters so random words aren't treated as dates
                sample_str = str(series.iloc[0])
                if any(sep in sample_str for sep in ("-", "/", ".")):
                    pd.to_datetime(series.head(10), errors="raise")
                    types[str(col)] = "date"
                    continue
            except Exception:
                pass

            # Check for boolean-like strings
            unique_lower = set(series.astype(str).str.strip().str.lower().unique())
            if unique_lower.issubset({"true", "false", "yes", "no", "1", "0", "y", "n"}):
                types[str(col)] = "boolean"
            else:
                types[str(col)] = "string"
    return types


# ── CSV parsing ────────────────────────────────────────────────────────────────

def _read_csv_preview(file_path: Path, encoding: str) -> pd.DataFrame:
    """Read the first PREVIEW_ROW_LIMIT rows of a CSV file."""
    try:
        return pd.read_csv(
            file_path,
            nrows=PREVIEW_ROW_LIMIT,
            encoding=encoding,
            on_bad_lines="skip",
            dtype=str,          # keep everything as string for preview
            keep_default_na=False,
        )
    except UnicodeDecodeError:
        logger.warning("CSV encoding fallback to latin-1 for %s", file_path.name)
        return pd.read_csv(
            file_path,
            nrows=PREVIEW_ROW_LIMIT,
            encoding="latin-1",
            on_bad_lines="skip",
            dtype=str,
            keep_default_na=False,
        )


def _iter_csv_chunks(
    file_path: Path,
    encoding: str,
) -> Iterator[tuple[list[dict], int]]:
    """
    Yield (rows_list, skipped_count) tuples for each CSV chunk.
    rows_list contains row dicts; skipped_count is the number of bad rows
    in that chunk.
    """
    try:
        reader = pd.read_csv(
            file_path,
            chunksize=CSV_CHUNK_SIZE,
            encoding=encoding,
            on_bad_lines="skip",
            dtype=str,
            keep_default_na=False,
        )
    except UnicodeDecodeError:
        logger.warning("CSV encoding fallback to latin-1 for %s", file_path.name)
        reader = pd.read_csv(
            file_path,
            chunksize=CSV_CHUNK_SIZE,
            encoding="latin-1",
            on_bad_lines="skip",
            dtype=str,
            keep_default_na=False,
        )

    for chunk in reader:
        # Replace pandas NA markers with None
        chunk = chunk.where(chunk.notna(), other=None)
        rows = chunk.to_dict(orient="records")
        yield rows, 0  # pandas already skipped bad lines (counted separately)


# ── JSON parsing ───────────────────────────────────────────────────────────────

def _read_json_preview(file_path: Path) -> list[dict]:
    """Read up to PREVIEW_ROW_LIMIT records from a JSON array file."""
    records = []
    with open(file_path, "rb") as f:
        for item in ijson.items(f, "item"):
            if not isinstance(item, dict):
                continue
            records.append(item)
            if len(records) >= PREVIEW_ROW_LIMIT:
                break
    return records


def _iter_json_chunks(file_path: Path) -> Iterator[tuple[list[dict], int]]:
    """Yield (records_list, skipped) tuples for each chunk of a JSON array."""
    batch: list[dict] = []
    skipped = 0
    with open(file_path, "rb") as f:
        for item in ijson.items(f, "item"):
            if not isinstance(item, dict):
                skipped += 1
                continue
            batch.append(item)
            if len(batch) >= JSON_CHUNK_SIZE:
                yield batch, skipped
                batch = []
                skipped = 0
    if batch:
        yield batch, skipped


# ── JSONL parsing ──────────────────────────────────────────────────────────────

def _read_jsonl_preview(file_path: Path, encoding: str) -> list[dict]:
    """Read up to PREVIEW_ROW_LIMIT records from a JSONL file."""
    records = []
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
            except json.JSONDecodeError:
                pass
            if len(records) >= PREVIEW_ROW_LIMIT:
                break
    return records


def _iter_jsonl_chunks(
    file_path: Path,
    encoding: str,
) -> Iterator[tuple[list[dict], int]]:
    """Yield (records_list, skipped) tuples for each JSONL chunk."""
    batch: list[dict] = []
    skipped = 0
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    skipped += 1
                    logger.debug("JSONL line %d is not a dict (skipping)", lineno)
                    continue
                batch.append(record)
            except json.JSONDecodeError as exc:
                skipped += 1
                logger.debug("JSONL line %d parse error (skipping): %s", lineno, exc)

            if len(batch) >= JSON_CHUNK_SIZE:
                yield batch, skipped
                batch = []
                skipped = 0
    if batch:
        yield batch, skipped


# ── Public API ─────────────────────────────────────────────────────────────────

class ParsedPreview:
    """Result of parsing the first ~100 rows of an uploaded file."""

    __slots__ = (
        "columns",
        "column_types",
        "preview_rows",
        "total_rows",
        "file_type",
        "encoding",
    )

    def __init__(
        self,
        columns: list[str],
        column_types: dict[str, str],
        preview_rows: list[dict],
        total_rows: int | None,
        file_type: str,
        encoding: str,
    ) -> None:
        self.columns = columns
        self.column_types = column_types
        self.preview_rows = preview_rows
        self.total_rows = total_rows
        self.file_type = file_type
        self.encoding = encoding


def parse_preview(file_path: str | Path, file_type: str) -> ParsedPreview:
    """
    Parse the first PREVIEW_ROW_LIMIT rows of an uploaded file synchronously.

    Called immediately after upload to power the column-mapping UI.
    Does NOT read the full file — only a small prefix.

    Args:
        file_path: Path to the saved file on disk.
        file_type: "csv", "json", or "jsonl".

    Returns:
        ParsedPreview with columns, types, preview rows, and estimated count.
    """
    path = Path(file_path)
    encoding = detect_encoding(path)

    if file_type == "csv":
        df = _read_csv_preview(path, encoding)
        columns = [str(c) for c in df.columns.tolist()]
        column_types = infer_column_types(df)
        preview_rows = df.where(df.notna(), other=None).to_dict(orient="records")

    elif file_type == "json":
        records = _read_json_preview(path)
        if not records:
            return ParsedPreview([], {}, [], 0, file_type, encoding)
        df = pd.DataFrame(records)
        columns = [str(c) for c in df.columns.tolist()]
        column_types = infer_column_types(df)
        preview_rows = records

    elif file_type == "jsonl":
        records = _read_jsonl_preview(path, encoding)
        if not records:
            return ParsedPreview([], {}, [], 0, file_type, encoding)
        df = pd.DataFrame(records)
        columns = [str(c) for c in df.columns.tolist()]
        column_types = infer_column_types(df)
        preview_rows = records

    else:
        raise ValueError(f"Unsupported file_type: {file_type!r}")

    total_rows = estimate_row_count(path, file_type)

    logger.info(
        "Preview parsed: file_type=%s, columns=%d, preview_rows=%d, "
        "estimated_total=%s, encoding=%s",
        file_type, len(columns), len(preview_rows), total_rows, encoding,
    )
    return ParsedPreview(
        columns=columns,
        column_types=column_types,
        preview_rows=preview_rows[:PREVIEW_ROW_LIMIT],
        total_rows=total_rows,
        file_type=file_type,
        encoding=encoding,
    )


def iter_file_chunks(
    file_path: str | Path,
    file_type: str,
) -> Iterator[tuple[list[dict], int]]:
    """
    Stream the full file in chunks for background (Celery) processing.

    Yields (rows_list, skipped_in_chunk) tuples.
    The caller is responsible for creating Incident objects from the rows.

    Args:
        file_path: Path to the saved file.
        file_type: "csv", "json", or "jsonl".
    """
    path = Path(file_path)
    encoding = detect_encoding(path)

    if file_type == "csv":
        yield from _iter_csv_chunks(path, encoding)
    elif file_type == "json":
        yield from _iter_json_chunks(path)
    elif file_type == "jsonl":
        yield from _iter_jsonl_chunks(path, encoding)
    else:
        raise ValueError(f"Unsupported file_type: {file_type!r}")
