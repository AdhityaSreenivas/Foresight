"""
PSIF Platform — Dataset Timing and ETA Engine

Provides robust, numerically stable timing metrics, throughput tracking,
and predictive ETA calculations for dataset processing jobs.

Design principles:
- Transparent separation between File Upload Duration and Dataset Processing Duration.
- Clock begins exactly when asynchronous processing starts and preserves across worker retries/reloads.
- No negative numbers, wild fluctuations, or NaN/overflow on datasets up to 1M+ rows.
- Warmup protection: displays "Estimating…" during early progress (< 1% or < 50 rows).
- Historical blending: uses completed jobs of the same file type to stabilize early throughput.
- Worker stall detection: pauses live countdown when heartbeat is lost or task is retrying.
- 100% backward-compatible with historical records (gracefully handles null timestamps).
"""
import logging
from typing import Optional
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Minimum progress thresholds before considering ETA reliable
MIN_PROGRESS_ROWS = 50
MIN_PROGRESS_PERCENT = 1.0

# Staleness threshold matching recovery service (seconds)
STALE_HEARTBEAT_THRESHOLD_SECONDS = 120

# Cache key and TTL for historical throughput stats
HISTORICAL_THROUGHPUT_CACHE_KEY = "foresight:datasets:historical_throughput"
HISTORICAL_THROUGHPUT_CACHE_TTL = 120  # 2 minutes


def format_seconds(seconds: Optional[float], is_estimate: bool = False) -> str:
    """
    Format a duration in seconds into a clean, human-friendly string.
    Rules:
      - < 60s: '42s' (or '~42s' if estimate)
      - 1m - 59m 59s: '4m 18s' (or '~4m 18s')
      - >= 60m: '1h 12m' (or '~1h 12m')
    No decimals or trailing precision noise.
    """
    if seconds is None:
        return ""
    
    total_sec = max(0, int(round(seconds)))
    prefix = "~" if is_estimate else ""

    if total_sec < 60:
        return f"{prefix}{total_sec}s"
    
    minutes = total_sec // 60
    remaining_sec = total_sec % 60

    if minutes < 60:
        if remaining_sec > 0:
            return f"{prefix}{minutes}m {remaining_sec:02d}s"
        return f"{prefix}{minutes}m"
    
    hours = minutes // 60
    remaining_min = minutes % 60
    if remaining_min > 0:
        return f"{prefix}{hours}h {remaining_min}m"
    return f"{prefix}{hours}h"


def get_historical_average_throughput(file_type: Optional[str] = None) -> Optional[float]:
    """
    Retrieve historical average processing throughput (rows/second) from completed datasets.
    Cached for 2 minutes to prevent repetitive database aggregation on every status poll.
    """
    from .models import Dataset

    cache_key = f"{HISTORICAL_THROUGHPUT_CACHE_KEY}:{file_type or 'all'}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val if cached_val > 0 else None

    try:
        qs = Dataset.objects.filter(
            status=Dataset.Status.COMPLETED,
            processing_duration_seconds__gt=0,
            processed_rows__gte=MIN_PROGRESS_ROWS,
        )
        if file_type:
            type_qs = qs.filter(file_type=file_type)
            if type_qs.exists():
                qs = type_qs

        total_rows = 0
        total_duration = 0.0
        for ds in qs.only("processed_rows", "processing_duration_seconds")[:50]:
            if ds.processed_rows and ds.processing_duration_seconds and ds.processing_duration_seconds > 0:
                total_rows += ds.processed_rows
                total_duration += ds.processing_duration_seconds

        if total_duration > 0 and total_rows > 0:
            avg_rate = round(total_rows / total_duration, 2)
            cache.set(cache_key, avg_rate, timeout=HISTORICAL_THROUGHPUT_CACHE_TTL)
            return avg_rate
        
        # Cache negative result briefly to avoid repeated queries
        cache.set(cache_key, -1, timeout=HISTORICAL_THROUGHPUT_CACHE_TTL)
        return None
    except Exception as exc:
        logger.debug("Failed to calculate historical throughput: %s", exc)
        return None


def calculate_dataset_timing(dataset, now=None) -> dict:
    """
    Calculate authoritative timing metrics, elapsed duration, throughput rate,
    and predicted ETA for a given Dataset instance.

    Thread-safe and pure derivation — does not write to the database.
    """
    from .models import Dataset

    if now is None:
        now = timezone.now()

    status = dataset.status
    started_at = dataset.processing_started_at
    completed_at = dataset.processing_completed_at or dataset.completed_at

    # Resilient fallback: For actively processing, retrying, or canceled datasets where
    # processing_started_at was not recorded, infer started_at from earliest incident or creation.
    if started_at is None and status in (
        Dataset.Status.PROCESSING,
        Dataset.Status.RETRYING,
        Dataset.Status.CANCEL_REQUESTED,
        Dataset.Status.CANCELED,
    ):
        if hasattr(dataset, "incidents") and dataset.incidents.exists():
            first_ts = dataset.incidents.order_by("created_at").values_list("created_at", flat=True).first()
            if first_ts:
                started_at = first_ts
        if started_at is None and dataset.created_at:
            started_at = dataset.created_at

    total_rows = dataset.total_rows
    processed_rows = dataset.processed_rows or 0

    # Default payload
    timing = {
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "elapsed_seconds": None,
        "formatted_elapsed": "",
        "processing_duration_seconds": dataset.processing_duration_seconds,
        "duration_seconds": dataset.processing_duration_seconds,
        "formatted_duration": "",
        "estimated_total_seconds": None,
        "estimated_remaining_seconds": None,
        "formatted_remaining": "",
        "formatted_total": "",
        "formatted_estimated_remaining": "",
        "formatted_estimated_total": "",
        "processing_rate_rows_per_second": None,
        "is_estimate_reliable": False,
        "estimate_source": "UNAVAILABLE",
        "is_stalled": False,
        "upload_duration_seconds": dataset.upload_duration_seconds,
        "formatted_upload_duration": format_seconds(dataset.upload_duration_seconds) if dataset.upload_duration_seconds else "",
        "summary": "",
    }

    def _finish(t):
        t["formatted_estimated_remaining"] = t.get("formatted_remaining", "")
        t["formatted_estimated_total"] = t.get("formatted_total", "")
        return t

    # ── CASE 1: Terminal COMPLETED ──────────────────────────────────────────
    if status == Dataset.Status.COMPLETED:
        duration = dataset.processing_duration_seconds
        if duration is None and started_at and completed_at:
            duration = max(0.0, (completed_at - started_at).total_seconds())

        if duration is not None:
            timing["elapsed_seconds"] = round(duration, 1)
            timing["processing_duration_seconds"] = round(duration, 1)
            timing["duration_seconds"] = round(duration, 1)
            timing["formatted_duration"] = format_seconds(duration)
            timing["formatted_elapsed"] = format_seconds(duration)
            timing["estimated_remaining_seconds"] = 0.0
            timing["formatted_remaining"] = "Completed"
            timing["estimate_source"] = "COMPLETED"
            timing["summary"] = f"Completed in {format_seconds(duration)}"
            if duration > 0 and processed_rows > 0:
                timing["processing_rate_rows_per_second"] = round(processed_rows / duration, 1)
        else:
            timing["formatted_remaining"] = "Completed"
            timing["estimate_source"] = "COMPLETED"
            timing["summary"] = "Completed · Duration unavailable"
        return _finish(timing)

    # ── CASE 2: Terminal FAILED ─────────────────────────────────────────────
    if status == Dataset.Status.FAILED:
        duration = dataset.processing_duration_seconds
        if duration is None and started_at and completed_at:
            duration = max(0.0, (completed_at - started_at).total_seconds())

        if duration is not None:
            timing["elapsed_seconds"] = round(duration, 1)
            timing["processing_duration_seconds"] = round(duration, 1)
            timing["duration_seconds"] = round(duration, 1)
            timing["formatted_duration"] = format_seconds(duration)
            timing["formatted_elapsed"] = format_seconds(duration)
            timing["estimate_source"] = "FAILED"
            timing["summary"] = f"Failed after {format_seconds(duration)}"
        else:
            timing["estimate_source"] = "FAILED"
            timing["summary"] = "Failed · Duration unavailable"
        return _finish(timing)

    # ── CASE 2B: Terminal CANCELED ──────────────────────────────────────────
    if status == Dataset.Status.CANCELED:
        duration = dataset.processing_duration_seconds
        end_ts = dataset.canceled_at or dataset.processing_completed_at or dataset.completed_at
        if duration is None and started_at and end_ts:
            duration = max(0.0, (end_ts - started_at).total_seconds())

        if duration is not None:
            timing["elapsed_seconds"] = round(duration, 1)
            timing["processing_duration_seconds"] = round(duration, 1)
            timing["duration_seconds"] = round(duration, 1)
            timing["formatted_duration"] = format_seconds(duration)
            timing["formatted_elapsed"] = format_seconds(duration)
            timing["estimated_remaining_seconds"] = 0.0
            timing["formatted_remaining"] = "Canceled"
            timing["estimate_source"] = "CANCELED"
            timing["summary"] = f"Canceled after {format_seconds(duration)}"
        else:
            timing["formatted_remaining"] = "Canceled"
            timing["estimate_source"] = "CANCELED"
            timing["summary"] = "Canceled"
        return _finish(timing)

    # ── CASE 3: Pre-processing (UPLOADED / MAPPING_PENDING) ──────────────────
    if status in (Dataset.Status.UPLOADED, Dataset.Status.MAPPING_PENDING):
        timing["estimate_source"] = "NOT_STARTED"
        timing["summary"] = "—"
        return _finish(timing)

    # ── CASE 4: Active States (PROCESSING / RETRYING / CANCEL_REQUESTED) ─────
    if started_at:
        elapsed = max(0.1, (now - started_at).total_seconds())
        timing["elapsed_seconds"] = round(elapsed, 1)
        timing["formatted_elapsed"] = format_seconds(elapsed)
    else:
        elapsed = None

    # Check for cancellation in flight
    if status == Dataset.Status.CANCEL_REQUESTED or getattr(dataset, "cancel_requested", False):
        timing["is_estimate_reliable"] = False
        timing["estimate_source"] = "CANCELING"
        timing["formatted_remaining"] = "Canceling… waiting for checkpoint"
        timing["summary"] = f"Canceling… · {timing['formatted_elapsed']} elapsed" if timing.get("formatted_elapsed") else "Canceling…"
        return _finish(timing)

    # Check for worker stall or heartbeat loss
    is_stalled = False
    if dataset.last_heartbeat_at:
        since_heartbeat = (now - dataset.last_heartbeat_at).total_seconds()
        if since_heartbeat > STALE_HEARTBEAT_THRESHOLD_SECONDS:
            is_stalled = True

    if status == Dataset.Status.RETRYING or is_stalled:
        timing["is_stalled"] = True
        timing["is_estimate_reliable"] = False
        timing["estimate_source"] = "RETRYING" if status == Dataset.Status.RETRYING else "STALLED"
        timing["formatted_remaining"] = "Processing paused / retrying…"
        timing["summary"] = f"Retrying · {timing['formatted_elapsed']} elapsed" if timing['formatted_elapsed'] else "Retrying"
        return _finish(timing)

    # If no start timestamp is available, we cannot compute live ETA
    if elapsed is None:
        timing["estimate_source"] = "UNAVAILABLE"
        timing["formatted_remaining"] = "Timing unavailable for current run"
        timing["summary"] = "Processing · Timing unavailable"
        return _finish(timing)

    # Check progress thresholds
    pct = (processed_rows / total_rows * 100.0) if (total_rows and total_rows > 0) else 0.0

    if processed_rows < MIN_PROGRESS_ROWS or pct < MIN_PROGRESS_PERCENT or not total_rows:
        # Early warmup / initial loading phase
        timing["is_estimate_reliable"] = False
        timing["estimate_source"] = "INITIAL_WARMUP"
        timing["formatted_remaining"] = "Estimating…"
        timing["summary"] = "Processing · Estimating…"
        if processed_rows > 0 and elapsed > 0:
            timing["processing_rate_rows_per_second"] = round(processed_rows / elapsed, 1)
        return _finish(timing)

    # ── Live Throughput & Smooth ETA Calculation ────────────────────────────
    live_rate = processed_rows / elapsed  # rows/sec

    # Blend with historical rate during initial 1% - 10% progress window
    hist_rate = get_historical_average_throughput(dataset.file_type)
    if hist_rate and hist_rate > 0 and pct < 10.0:
        # Alpha moves smoothly from 0.0 (at 1%) to 1.0 (at 10%)
        alpha = max(0.0, min(1.0, (pct - MIN_PROGRESS_PERCENT) / (10.0 - MIN_PROGRESS_PERCENT)))
        effective_rate = (1.0 - alpha) * hist_rate + alpha * live_rate
        estimate_source = "HISTORICAL_ASSISTED"
    else:
        effective_rate = live_rate
        estimate_source = "LIVE_THROUGHPUT"

    if effective_rate > 0:
        remaining_rows = max(0, total_rows - processed_rows)
        raw_remaining = remaining_rows / effective_rate
        raw_total = total_rows / effective_rate

        # Clamping
        estimated_remaining_seconds = max(0.0, round(raw_remaining, 1))
        estimated_total_seconds = max(round(elapsed, 1), round(raw_total, 1))

        timing["processing_rate_rows_per_second"] = round(effective_rate, 1)
        timing["estimated_remaining_seconds"] = estimated_remaining_seconds
        timing["estimated_total_seconds"] = estimated_total_seconds
        timing["formatted_remaining"] = format_seconds(estimated_remaining_seconds, is_estimate=True)
        timing["formatted_total"] = format_seconds(estimated_total_seconds, is_estimate=True)
        timing["is_estimate_reliable"] = True
        timing["estimate_source"] = estimate_source
        timing["summary"] = f"Processing · {timing['formatted_remaining']} remaining"
    else:
        timing["formatted_remaining"] = "Estimating…"
        timing["summary"] = "Processing · Estimating…"

    return _finish(timing)
