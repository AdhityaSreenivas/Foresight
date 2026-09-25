import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from core.ml.pipeline import run_pipeline
from .file_parser import extract_text_from_file
from .models import SafetyReport

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def home(request):
    result = None

    if request.method == "POST":
        text = request.POST.get("report_text", "").strip()
        if text:
            try:
                result = run_pipeline(text)
                result["text"] = text
            except Exception as error:
                result = {
                    "error": str(error),
                    "text": text
                }

    return render(
        request,
        "core/index.html",
        {
            "result": result
        }
    )


def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        first_name = request.POST.get("first_name", "").strip()

        if username and password:
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name
                )
                login(request, user)
                return redirect("home")

    return render(
        request,
        "core/register.html"
    )


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("home")

        return render(
            request,
            "core/login.html",
            {
                "error": "Invalid username or password."
            }
        )

    return render(
        request,
        "core/login.html"
    )


def logout_view(request):
    logout(request)
    return redirect("login")


@require_POST
def analyze_report(request):
    report_text = request.POST.get("report_text", "").strip()
    site_area = request.POST.get("site_area", "").strip()

    if not report_text:
        return JsonResponse({"error": "No report text provided."}, status=400)

    try:
        # Run trained ML + NLP Pipeline
        result = run_pipeline(report_text)

        rule = result.get("life_saving_rule", "Unclassified")
        lsr_prob = float(result.get("lsr_probability", 0.0))
        lsr_src = result.get("lsr_source", "ml")
        activity_val = result.get("activity", "General Operations")
        activity_prob = float(result.get("activity_probability", 0.0))

        report_id = None
        try:
            saved_report = SafetyReport.objects.create(
                report_text=report_text,
                classification=result.get("classification", "NON-SIF"),
                is_sif=bool(result.get("is_sif", False)),
                confidence=float(result.get("confidence", 0.0)),
                sif_probability=float(result.get("sif_probability", 0.0)),
                non_sif_probability=float(result.get("non_sif_probability", 0.0)),
                risk_level=result.get("risk_level", "LOW"),
                life_saving_rule=rule,
                lsr_probability=lsr_prob,
                lsr_source=lsr_src,
                activity=activity_val,
                activity_probability=activity_prob,
                site_area=site_area,
                precursors=result.get("precursors", []),
                evidence=result.get("evidence", []),
                barrier_failures=result.get("barrier_failures", []),
                reason=result.get("reason", ""),
                potential_consequence=result.get("potential_consequence", ""),
                recommended_measures=result.get("recommended_measures", []),
            )
            report_id = saved_report.id
        except Exception as db_error:
            logger.error(f"DB Save error: Failed to save SafetyReport: {db_error}", exc_info=True)

        return JsonResponse(
            {
                "id": report_id,
                "classification": result.get("classification", "NON-SIF"),
                "is_sif": bool(result.get("is_sif", False)),
                "confidence": float(result.get("confidence", 0.0)),
                "sif_probability": float(result.get("sif_probability", 0.0)),
                "non_sif_probability": float(result.get("non_sif_probability", 0.0)),
                "life_saving_rule": rule,
                "lsr_probability": lsr_prob,
                "lsr_source": lsr_src,
                "rule": rule,  # backward compatibility
                "activity": activity_val,
                "activity_probability": activity_prob,
                "site_area": site_area,
                "precursors": result.get("precursors", []),
                "evidence": result.get("evidence", []),
                "barrier_failures": result.get("barrier_failures", []),
                "risk_level": result.get("risk_level", "LOW"),
                "reason": result.get("reason", ""),
                "potential_consequence": result.get("potential_consequence", ""),
                "recommended_measures": result.get("recommended_measures", []),
            }
        )

    except Exception as error:
        return JsonResponse(
            {
                "error": f"AI analysis failed: {str(error)}"
            },
            status=500
        )


@require_POST
def upload_reports(request):
    uploaded_files = request.FILES.getlist("files")

    if not uploaded_files:
        return JsonResponse(
            {
                "success": False,
                "error": "No files were uploaded."
            },
            status=400
        )

    reports = []

    for uploaded_file in uploaded_files:
        try:
            extracted_reports = extract_text_from_file(uploaded_file)
            for text in extracted_reports:
                text = text.strip()
                if text:
                    reports.append(
                        {
                            "text": text,
                            "filename": uploaded_file.name
                        }
                    )
        except Exception as error:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Could not process {uploaded_file.name}: {error}"
                },
                status=400
            )

    return JsonResponse(
        {
            "success": True,
            "count": len(reports),
            "reports": reports
        }
    )


def history_view(request):
    try:
        reports = SafetyReport.objects.all().order_by("-created_at")
        data = [
            {
                "id": r.id,
                "report_text": r.report_text,
                "classification": r.classification,
                "is_sif": r.is_sif,
                "confidence": r.confidence,
                "sif_probability": r.sif_probability,
                "non_sif_probability": r.non_sif_probability,
                "risk_level": r.risk_level,
                "life_saving_rule": r.life_saving_rule,
                "lsr_probability": r.lsr_probability,
                "lsr_source": r.lsr_source,
                "activity": r.activity,
                "activity_probability": r.activity_probability,
                "site_area": r.site_area,
                "precursors": r.precursors or [],
                "evidence": r.evidence or [],
                "barrier_failures": r.barrier_failures or [],
                "reason": r.reason or "",
                "potential_consequence": r.potential_consequence or "",
                "recommended_measures": r.recommended_measures or [],
                "created_at": r.created_at.strftime("%d %b %Y, %I:%M %p") if r.created_at else "",
                "created_at_iso": r.created_at.isoformat() if r.created_at else "",
            }
            for r in reports
        ]
        return JsonResponse({"success": True, "reports": data})
    except Exception as error:
        logger.error(f"Error fetching history: {error}", exc_info=True)
        return JsonResponse({"success": False, "error": f"Failed to retrieve history: {str(error)}"}, status=500)


def pattern_analytics_view(request):
    """
    Calculates recurring precursor and barrier failure patterns from real PostgreSQL SafetyReport records.
    """
    from collections import Counter
    try:
        reports = SafetyReport.objects.all()

        total_reports = reports.count()
        sif_reports = reports.filter(is_sif=True).count()

        precursor_counter = Counter()
        barrier_counter = Counter()
        lsr_counter = Counter()
        activity_counter = Counter()
        activity_precursor_map = Counter()

        for r in reports:
            if r.life_saving_rule and r.life_saving_rule != "Unclassified":
                lsr_counter[r.life_saving_rule] += 1

            if r.activity:
                activity_counter[r.activity] += 1

            for p in (r.precursors or []):
                pname = p.get("name") if isinstance(p, dict) else str(p)
                if pname:
                    precursor_counter[pname] += 1
                    if r.activity:
                        activity_precursor_map[f"{r.activity} -> {pname}"] += 1

            for bf in (r.barrier_failures or []):
                if bf and bf != "None detected":
                    barrier_counter[bf] += 1

        analytics = {
            "total_reports": total_reports,
            "sif_reports": sif_reports,
            "sif_rate": round((sif_reports / total_reports * 100), 2) if total_reports > 0 else 0.0,
            "top_precursors": [{"name": k, "count": v} for k, v in precursor_counter.most_common(5)],
            "top_barrier_failures": [{"failure": k, "count": v} for k, v in barrier_counter.most_common(5)],
            "lsr_distribution": [{"lsr": k, "count": v} for k, v in lsr_counter.most_common()],
            "activity_distribution": [{"activity": k, "count": v} for k, v in activity_counter.most_common()],
            "top_activity_precursors": [{"combo": k, "count": v} for k, v in activity_precursor_map.most_common(5)],
        }

        return JsonResponse({"success": True, "analytics": analytics})
    except Exception as error:
        logger.error(f"Error computing pattern analytics: {error}", exc_info=True)
        return JsonResponse({"success": False, "error": f"Failed to calculate analytics: {str(error)}"}, status=500)

