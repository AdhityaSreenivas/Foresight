"""
PSIF Platform — Model Retraining Timing and ETA Engine

Provides robust, numerically stable timing metrics, throughput tracking,
and predictive ETA calculations for model retraining jobs.

Key Principles:
- Started_at is recorded once when retraining begins and is never reset by polling or refresh.
- Throughput is derived from real completed units (e.g. DistilBERT text embeddings).
- Post-embedding phases are projected based on measured throughput and real computational weights.
- Exponential moving average (EMA) smoothing prevents wild jumps in ETA.
- Completed training runs freeze duration.
- Historical models without timing data gracefully return 'Duration unavailable'.
- Concurrency: Every model version tracks its timing state independently within its own metrics dict.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

HISTORICAL_TRAINING_CACHE_KEY = "foresight:retraining:historical_stats"
HISTORICAL_TRAINING_CACHE_TTL = 120  # 2 minutes


def format_seconds(seconds: Optional[float], is_estimate: bool = False) -> str:
    """
    Format a duration in seconds into a clean, human-friendly string.
    Rules:
      - None: ""
      - < 60s: '42s' (or '~42s' if estimate)
      - 1m - 59m 59s: '4m 18s' (or '~4m 18s')
      - >= 60m: '1h 12m' (or '~1h 12m')
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


def get_historical_training_rate() -> Optional[float]:
    """
    Retrieve historical average training rate (samples / second) across completed runs.
    Cached for 2 minutes to minimize DB overhead on polling.
    """
    from apps.predictions.models import ModelVersion

    cached = cache.get(HISTORICAL_TRAINING_CACHE_KEY)
    if cached is not None:
        return cached if cached > 0 else None

    try:
        models = ModelVersion.objects.filter(
            status__in=[ModelVersion.Status.READY, ModelVersion.Status.ACTIVE]
        ).exclude(metrics__isnull=True)[:20]

        total_samples = 0
        total_seconds = 0.0

        for m in models:
            metrics = m.metrics or {}
            dur = metrics.get("training_duration_seconds")
            samples = metrics.get("total_labeled_rows") or metrics.get("training_set_size")
            if dur and samples and dur > 0 and samples > 0:
                total_samples += samples
                total_seconds += float(dur)

        if total_seconds > 0 and total_samples > 0:
            rate = round(total_samples / total_seconds, 2)
            cache.set(HISTORICAL_TRAINING_CACHE_KEY, rate, timeout=HISTORICAL_TRAINING_CACHE_TTL)
            return rate
    except Exception as exc:
        logger.debug("Could not calculate historical training rate: %s", exc)

    return None


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO formatted datetime string safely into a timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        return dt
    except Exception:
        return None


def calculate_retraining_timing(
    model_version,
    current_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute authoritative timing, throughput, and smoothed ETA for a ModelVersion.
    
    Returns a dictionary of timing fields:
      - elapsed_seconds: int or None
      - estimated_remaining_seconds: int or None
      - estimated_total_seconds: int or None
      - estimate_source: str ("LIVE_THROUGHPUT" | "HISTORICAL_MODEL" | "ESTIMATING" | "FROZEN_COMPLETED")
      - formatted_elapsed: str
      - formatted_remaining: str
      - formatted_total: str
      - formatted_duration: str
    """
    metrics = current_metrics if current_metrics is not None else (model_version.metrics or {})
    st = getattr(model_version, "status", None) or metrics.get("training_status", "PENDING")

    # ── CASE 1: COMPLETED (READY or ACTIVE) ───────────────────────────────────
    if st in (getattr(model_version, "Status", None) and model_version.Status.READY,
              getattr(model_version, "Status", None) and model_version.Status.ACTIVE,
              "READY", "ACTIVE"):
        duration_sec = metrics.get("training_duration_seconds")
        if duration_sec is None:
            started_at = parse_iso_datetime(metrics.get("started_at"))
            completed_at = parse_iso_datetime(metrics.get("completed_at"))
            if started_at and completed_at and completed_at >= started_at:
                duration_sec = round((completed_at - started_at).total_seconds(), 1)

        if duration_sec is not None and duration_sec > 0:
            formatted_dur = f"Completed in {format_seconds(duration_sec)}"
            dur_int = int(round(duration_sec))
            return {
                "elapsed_seconds": dur_int,
                "estimated_remaining_seconds": 0,
                "estimated_total_seconds": dur_int,
                "estimate_source": "FROZEN_COMPLETED",
                "formatted_elapsed": format_seconds(dur_int),
                "formatted_remaining": "0s",
                "formatted_total": format_seconds(dur_int),
                "formatted_duration": formatted_dur,
                "training_duration_seconds": duration_sec,
            }
        else:
            return {
                "elapsed_seconds": None,
                "estimated_remaining_seconds": 0,
                "estimated_total_seconds": None,
                "estimate_source": "FROZEN_COMPLETED",
                "formatted_elapsed": "—",
                "formatted_remaining": "0s",
                "formatted_total": "—",
                "formatted_duration": "Duration unavailable",
                "training_duration_seconds": None,
            }

    # ── CASE 2: FAILED ────────────────────────────────────────────────────────
    if st in ("FAILED", getattr(model_version, "Status", None) and model_version.Status.FAILED):
        duration_sec = metrics.get("training_duration_seconds")
        if duration_sec is None:
            started_at = parse_iso_datetime(metrics.get("started_at"))
            failed_at = parse_iso_datetime(metrics.get("failed_at"))
            if started_at and failed_at and failed_at >= started_at:
                duration_sec = round((failed_at - started_at).total_seconds(), 1)

        if duration_sec is not None and duration_sec > 0:
            formatted_dur = f"Failed after {format_seconds(duration_sec)}"
            return {
                "elapsed_seconds": int(round(duration_sec)),
                "estimated_remaining_seconds": 0,
                "estimated_total_seconds": int(round(duration_sec)),
                "estimate_source": "FAILED",
                "formatted_elapsed": format_seconds(duration_sec),
                "formatted_remaining": "0s",
                "formatted_total": format_seconds(duration_sec),
                "formatted_duration": formatted_dur,
                "training_duration_seconds": duration_sec,
            }
        else:
            return {
                "elapsed_seconds": None,
                "estimated_remaining_seconds": 0,
                "estimated_total_seconds": None,
                "estimate_source": "FAILED",
                "formatted_elapsed": "—",
                "formatted_remaining": "0s",
                "formatted_total": "—",
                "formatted_duration": "Duration unavailable",
                "training_duration_seconds": None,
            }

    # ── CASE 3: ACTIVE RETRAINING (RUNNING or PENDING) ─────────────────────────
    now = timezone.now()
    started_at = parse_iso_datetime(metrics.get("started_at"))
    if not started_at:
        started_at = parse_iso_datetime(metrics.get("enqueued_at"))
    if not started_at and hasattr(model_version, "trained_at"):
        started_at = model_version.trained_at

    elapsed_seconds = max(0, int(round((now - started_at).total_seconds()))) if started_at else 0
    progress_pct = int(metrics.get("progress_pct") or (10 if st == "RUNNING" else 2))
    progress_pct = max(0, min(100, progress_pct))
    stage_code = metrics.get("stage_code") or ""
    processed_units = metrics.get("processed_units")
    total_units = metrics.get("total_units")

    # Early stage warmup check
    if elapsed_seconds < 3 or progress_pct < 5:
        return {
            "elapsed_seconds": elapsed_seconds,
            "estimated_remaining_seconds": None,
            "estimated_total_seconds": None,
            "estimate_source": "ESTIMATING",
            "formatted_elapsed": format_seconds(elapsed_seconds),
            "formatted_remaining": "Estimating remaining time…",
            "formatted_total": "Estimating…",
            "formatted_duration": "In progress",
            "training_duration_seconds": None,
        }

    raw_remaining: Optional[float] = None
    estimate_source = "LIVE_THROUGHPUT"

    # 1. High-precision throughput during DistilBERT Training Embeddings
    if stage_code == "EMBEDDING_TRAIN" and processed_units and total_units and processed_units > 0:
        emb_start = parse_iso_datetime(metrics.get("emb_train_started_at")) or started_at
        phase_elapsed = max(1.0, (now - emb_start).total_seconds())
        throughput = processed_units / phase_elapsed  # samples/sec

        if throughput > 0:
            rem_train_units = max(0, total_units - processed_units)
            rem_train_time = rem_train_units / throughput
            # Held-out 15% evaluation split text encoding workload:
            test_units = int(round(total_units * (0.15 / 0.85)))
            test_emb_time = test_units / throughput
            # Post-embedding phases (approx 35% of overall compute runtime):
            # Total embedding time is (train + test) / throughput
            total_emb_time = (total_units + test_units) / throughput
            # Downstream phases (feature fusion, XGBoost CV, OOF threshold, final fit, evaluation):
            post_emb_time = max(8.0, total_emb_time * (0.35 / 0.55))
            raw_remaining = rem_train_time + test_emb_time + post_emb_time
            estimate_source = "LIVE_THROUGHPUT"

    # 2. High-precision throughput during DistilBERT Test Embeddings
    elif stage_code == "EMBEDDING_TEST" and processed_units and total_units and processed_units > 0:
        emb_test_start = parse_iso_datetime(metrics.get("emb_test_started_at")) or started_at
        phase_elapsed = max(1.0, (now - emb_test_start).total_seconds())
        throughput = processed_units / phase_elapsed
        if throughput > 0:
            rem_test_units = max(0, total_units - processed_units)
            rem_test_time = rem_test_units / throughput
            # Downstream phases remaining
            post_emb_time = max(8.0, (elapsed_seconds / 0.65) * 0.35)
            raw_remaining = rem_test_time + post_emb_time
            estimate_source = "LIVE_THROUGHPUT"

    # 3. Post-embedding or phase-weighted throughput
    if raw_remaining is None:
        if progress_pct > 0:
            # Extrapolate from completed progress percentage
            effective_pct = max(progress_pct, 5)
            estimated_total = (elapsed_seconds / effective_pct) * 100.0
            raw_remaining = max(3.0, estimated_total - elapsed_seconds)
            estimate_source = "LIVE_THROUGHPUT"
        else:
            hist_rate = get_historical_training_rate()
            if hist_rate and total_units:
                estimated_total = total_units / hist_rate
                raw_remaining = max(5.0, estimated_total - elapsed_seconds)
                estimate_source = "HISTORICAL_MODEL"
            else:
                raw_remaining = None
                estimate_source = "ESTIMATING"

    if raw_remaining is None:
        return {
            "elapsed_seconds": elapsed_seconds,
            "estimated_remaining_seconds": None,
            "estimated_total_seconds": None,
            "estimate_source": "ESTIMATING",
            "formatted_elapsed": format_seconds(elapsed_seconds),
            "formatted_remaining": "Estimating remaining time…",
            "formatted_total": "Estimating…",
            "formatted_duration": "In progress",
            "training_duration_seconds": None,
        }

    # ── Smoothing: Exponential Moving Average (EMA) ───────────────────────────
    prev_smoothed = metrics.get("smoothed_eta_seconds")
    if prev_smoothed is not None:
        try:
            prev_float = float(prev_smoothed)
            alpha = 0.25
            smoothed = alpha * raw_remaining + (1.0 - alpha) * prev_float
            # Clamp jump to prevent erratic visual fluctuations (max 25% change or 8s per update)
            max_delta = max(8.0, prev_float * 0.25)
            smoothed = max(prev_float - max_delta, min(prev_float + max_delta, smoothed))
        except (ValueError, TypeError):
            smoothed = raw_remaining
    else:
        smoothed = raw_remaining

    smoothed_remaining_sec = max(1, int(round(smoothed)))
    estimated_total_sec = max(elapsed_seconds + 1, int(round(elapsed_seconds + smoothed_remaining_sec)))

    return {
        "elapsed_seconds": elapsed_seconds,
        "estimated_remaining_seconds": smoothed_remaining_sec,
        "estimated_total_seconds": estimated_total_sec,
        "estimate_source": estimate_source,
        "formatted_elapsed": format_seconds(elapsed_seconds, is_estimate=False),
        "formatted_remaining": format_seconds(smoothed_remaining_sec, is_estimate=True),
        "formatted_total": format_seconds(estimated_total_sec, is_estimate=True),
        "formatted_duration": "In progress",
        "training_duration_seconds": None,
        "smoothed_eta_seconds": round(smoothed, 1),
    }
