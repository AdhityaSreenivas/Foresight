from core.ml.embed import get_embedding
from core.ml.classify import classify_report
from core.ml.lsr_classifier import predict_lsr
from core.ml.activity_classifier import predict_activity
from core.ml.precursor import detect_precursors, extract_barrier_failures
from core.ml.evidence import extract_evidence


def run_pipeline(text):
    text = text.strip()

    if not text:
        raise ValueError("Report text cannot be empty.")

    # =========================================================
    # 1. GENERATE SINGLE ROBERTA EMBEDDING (768D)
    # =========================================================
    embedding = get_embedding(text)

    # =========================================================
    # 2. RUN ML CLASSIFIERS USING SHARED EMBEDDING
    # =========================================================
    sif_res = classify_report(text, embedding=embedding)
    lsr_res = predict_lsr(text=text, embedding=embedding)
    activity_res = predict_activity(text=text, embedding=embedding)

    is_sif = bool(sif_res.get("is_sif", False))
    sif_prob = float(sif_res.get("sif_probability", 0.0))
    non_sif_prob = float(sif_res.get("non_sif_probability", 0.0))
    confidence = float(sif_res.get("confidence", 0.0))

    # =========================================================
    # 3. RUN NLP ANALYSIS (Precursors, Barriers, Evidence)
    # =========================================================
    precursors = detect_precursors(text)
    evidence = extract_evidence(text, precursors)
    barrier_failures = extract_barrier_failures(text, precursors)

    # =========================================================
    # 4. RISK LEVEL AGGREGATION
    # =========================================================
    severities = []
    for p in precursors:
        if isinstance(p, dict) and p.get("severity"):
            severities.append(p.get("severity").upper())

    if "CRITICAL" in severities:
        risk_level = "CRITICAL"
    elif "HIGH" in severities or (is_sif and sif_prob >= 0.80):
        risk_level = "HIGH"
    elif "MEDIUM" in severities or (is_sif and sif_prob >= 0.50):
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # =========================================================
    # 5. REASON, CONSEQUENCE, RECOMMENDATIONS
    # =========================================================
    precursor_names = [p.get("name", "") for p in precursors if isinstance(p, dict)]
    lsr_name = lsr_res.get("life_saving_rule", "Unclassified")
    act_name = activity_res.get("activity", "General Operations")

    if is_sif:
        reason = f"Detected high-risk precursors ({', '.join(precursor_names) if precursor_names else 'SIF conditions'}) associated with {lsr_name} during {act_name}."
        potential_consequence = f"High potential for severe injury or fatality during {act_name} related to {lsr_name}."
        recommendations = [
            f"Enforce strict adherence to {lsr_name} rules.",
            "Verify all energy isolations, gas tests, and permits prior to work.",
            "Conduct safety stand-down and toolbox talk with operating personnel."
        ]
    else:
        reason = "No critical SIF precursors detected in report."
        potential_consequence = "Low potential for severe injury or fatality."
        recommendations = [
            "Continue standard safe work practices.",
            "Report any changes in operational risk or environment."
        ]

    return {
        "classification": sif_res.get("classification", "NON-SIF"),
        "is_sif": is_sif,
        "confidence": confidence,
        "sif_probability": sif_prob,
        "non_sif_probability": non_sif_prob,

        "life_saving_rule": lsr_name,
        "lsr_probability": float(lsr_res.get("lsr_probability", 0.0)),
        "lsr_source": lsr_res.get("source", "ml"),
        "lsr": lsr_name,  # for backward compatibility

        "activity": act_name,
        "activity_probability": float(activity_res.get("activity_probability", 0.0)),
        "activity_source": activity_res.get("source", "ml"),

        "precursors": precursors,
        "evidence": evidence,
        "barrier_failures": barrier_failures,

        "risk_level": risk_level,
        "reason": reason,
        "potential_consequence": potential_consequence,
        "recommended_measures": recommendations
    }