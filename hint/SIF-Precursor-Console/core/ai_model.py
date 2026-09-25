LSR_RULES = {
    "Energy Isolation": [
        "isolation",
        "isolated",
        "loto",
        "lockout",
        "lock out",
        "energy",
        "valve",
        "electrical",
        "de-energized",
        "deenergized",
    ],

    "Confined Space": [
        "confined space",
        "tank",
        "vessel",
        "enclosed space",
        "gas monitor",
        "gas monitoring",
        "entry permit",
        "oxygen",
        "toxic gas",
    ],

    "Hot Work": [
        "hot work",
        "welding",
        "weld",
        "cutting",
        "spark",
        "flame",
        "grinding",
    ],

    "Line of Fire": [
        "line of fire",
        "suspended load",
        "dropped object",
        "struck by",
        "falling object",
        "overhead load",
    ],

    "Working at Height": [
        "working at height",
        "height",
        "scaffold",
        "scaffolding",
        "ladder",
        "harness",
        "fall",
        "elevated",
    ],

    "Lifting Operations": [
        "crane",
        "lifting",
        "lifting operation",
        "sling",
        "rigger",
        "hoist",
        "load",
    ],

    "Driving": [
        "vehicle",
        "driving",
        "speeding",
        "speed",
        "seatbelt",
        "truck",
        "road",
        "forklift",
    ],

    "Bypassing Safety Controls": [
        "bypass",
        "bypassed",
        "override",
        "disabled alarm",
        "safety control disabled",
        "defeat",
    ],
}


BARRIER_FAILURES = [
    "without",
    "not worn",
    "not isolated",
    "isolation not confirmed",
    "not confirmed",
    "no permit",
    "no gas monitor",
    "without gas monitor",
    "no barricade",
    "not barricaded",
    "did not",
    "failed",
    "unattended",
    "unsafe condition",
]


def predict_sif(text):

    text = text.lower().strip()

    # ==========================================
    # 1. Detect Life-Saving Rule
    # ==========================================

    rule_scores = {}

    for rule, keywords in LSR_RULES.items():

        score = 0

        for keyword in keywords:
            if keyword in text:
                score += 1

        rule_scores[rule] = score

    matched_rule = max(
        rule_scores,
        key=rule_scores.get
    )

    rule_hits = rule_scores[matched_rule]

    # ==========================================
    # 2. Detect barrier failures
    # ==========================================

    barrier_failures = []

    for phrase in BARRIER_FAILURES:

        if phrase in text:
            barrier_failures.append(phrase)

    # ==========================================
    # 3. Additional high-risk evidence
    # ==========================================

    HIGH_RISK_TERMS = [
        "gas leak",
        "gas leakage",
        "toxic gas",
        "oxygen deficient",
        "oxygen deficiency",
        "worker died",
        "fatality",
        "death",
        "serious injury",
        "unconscious",
        "explosion",
        "fire",
        "electrocution",
        "crushed",
        "trapped",
        "fell from height",
        "fall from height",
        "dropped load",
        "vehicle collision",
    ]

    high_risk_hits = []

    for phrase in HIGH_RISK_TERMS:

        if phrase in text:
            high_risk_hits.append(phrase)

    # ==========================================
    # 4. Calculate risk score
    # ==========================================

    risk_score = 0

    # Recognized hazardous activity
    if rule_hits > 0:
        risk_score += min(rule_hits * 0.20, 0.60)

    # Barrier failure
    risk_score += min(
        len(barrier_failures) * 0.15,
        0.45
    )

    # Serious consequence / high-risk evidence
    risk_score += min(
        len(high_risk_hits) * 0.20,
        0.40
    )

    # ==========================================
    # 7. SIF decision
    # ==========================================
    
    actual_fatality = any(phrase in text for phrase in ["worker died", "fatality", "death", "fatal"])

    is_sif = (
        risk_score >= 0.35
        and (
            rule_hits >= 1
            or len(high_risk_hits) >= 1
        )
    )

    # ==========================================
    # 6. Confidence
    # ==========================================

    confidence = min(
        0.95,
        max(
            0.15,
            0.50 + risk_score * 0.45
        )
    )

    if actual_fatality:
        return {
            "classification": "ACTUAL FATAL EVENT",
            "is_sif": False,
            "confidence": 0.99,
            "rule": matched_rule if rule_hits > 0 else "High Consequence Event",
            "barrier_failures": barrier_failures[:3] if barrier_failures else high_risk_hits[:3],
        }

    # ==========================================
    # 7. NON-SIF
    # ==========================================

    if not is_sif:

        return {
            "classification": "NON-SIF",
            "is_sif": False,
            "confidence": round(
                1 - confidence + 0.25,
                2
            ),
            "rule": (
                matched_rule
                if rule_hits > 0
                else "Unclassified"
            ),
            "barrier_failures": (
                barrier_failures[:3]
                if barrier_failures
                else high_risk_hits[:3]
            ),
        }

    # ==========================================
    # 8. SIF-POTENTIAL
    # ==========================================

    return {
        "classification": "SIF-POTENTIAL",
        "is_sif": True,
        "confidence": round(
            confidence,
            2
        ),
        "rule": (
            matched_rule
            if rule_hits > 0
            else "High Consequence Event"
        ),
        "barrier_failures": (
            barrier_failures[:3]
            if barrier_failures
            else high_risk_hits[:3]
        ),
    }