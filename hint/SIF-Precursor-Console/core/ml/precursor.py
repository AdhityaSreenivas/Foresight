import re


PRECURSOR_RULES = {
    "confined_space": {
        "name": "Confined Space",
        "keywords": [
            "confined space",
            "tank entry",
            "vessel entry",
            "manhole entry",
            "entered the tank",
            "confined",
        ],
        "severity": "CRITICAL",
    },
    "energy_isolation": {
        "name": "Failure of Energy Isolation",
        "keywords": [
            "isolation not verified",
            "without isolation",
            "lockout",
            "lock out",
            "loto",
            "energy isolation",
            "equipment was not isolated",
            "electrical isolation",
            "confirming isolation",
            "isolation",
            "isolated",
        ],
        "severity": "CRITICAL",
    },
    "gas_testing": {
        "name": "Missing Gas Testing",
        "keywords": [
            "gas testing",
            "gas test",
            "atmospheric testing",
            "gas detection",
            "oxygen testing",
            "gas monitoring",
            "gas monitor",
        ],
        "severity": "HIGH",
    },
    "working_at_height": {
        "name": "Working at Height",
        "keywords": [
            "working at height",
            "fall from height",
            "scaffold",
            "scaffolding",
            "ladder",
            "elevated platform",
            "harness",
            "fall protection",
        ],
        "severity": "HIGH",
    },
    "line_of_fire": {
        "name": "Line of Fire",
        "keywords": [
            "line of fire",
            "struck by",
            "caught between",
            "pinch point",
            "moving equipment",
            "suspended load",
            "dropped object",
        ],
        "severity": "HIGH",
    },
    "lifting": {
        "name": "Lifting Operation",
        "keywords": [
            "lifting",
            "crane",
            "suspended load",
            "lifting operation",
            "rigging",
            "rigger",
        ],
        "severity": "HIGH",
    },
    "hot_work": {
        "name": "Hot Work",
        "keywords": [
            "hot work",
            "welding",
            "weld",
            "cutting",
            "spark",
            "grinding",
            "torch",
        ],
        "severity": "HIGH",
    },
    "driving_transport": {
        "name": "Driving & Transport",
        "keywords": [
            "driving",
            "driver",
            "vehicle",
            "speeding",
            "seatbelt",
            "truck",
            "collision",
        ],
        "severity": "HIGH",
    },
    "bypassing_controls": {
        "name": "Bypassing Safety Controls",
        "keywords": [
            "bypassed",
            "bypassing",
            "override",
            "disabled alarm",
            "interlock bypassed",
            "safety device disabled",
        ],
        "severity": "CRITICAL",
    },
}


def detect_precursors(text):
    text_lower = text.lower()
    detected = []

    for precursor_id, rule in PRECURSOR_RULES.items():
        matched_keywords = []

        for keyword in rule["keywords"]:
            if keyword.lower() in text_lower:
                matched_keywords.append(keyword)

        if matched_keywords:
            detected.append({
                "id": precursor_id,
                "name": rule["name"],
                "severity": rule["severity"],
                "matched_keywords": matched_keywords,
            })

    return detected


BARRIER_FAILURE_PATTERNS = [
    (r"without\s+(?:gas\s+test(?:ing)?|gas\040monitor|atmospheric\040testing)", "Gas testing not performed"),
    (r"(?:isolation\s+not\s+verified|without\s+isolation|isolation\s+failed|not\s+isolated)", "Isolation not verified"),
    (r"(?:without\s+fall\s+protection|without\s+(?:harness|lanyard)|no\s+fall\s+protection)", "Fall protection missing"),
    (r"(?:without\s+permit|no\s+(?:work\s+)?permit|permit\s+not\s+issued)", "Work permit not obtained"),
    (r"(?:without\s+(?:required\s+)?hot\s+work\s+controls|hot\s+work\s+permit\s+missing)", "Hot work controls missing"),
    (r"(?:without\s+seatbelt|speeding|reckless\s+driving)", "Driving safety controls violated"),
    (r"(?:bypassed|override|disabled)\s+(?:safety\s+controls?|alarm|interlock|guard)", "Safety control bypassed"),
]


def extract_barrier_failures(text, precursors=None):
    text_lower = text.lower()
    failures = []

    for pattern, label in BARRIER_FAILURE_PATTERNS:
        if re.search(pattern, text_lower):
            failures.append(label)

    # General phrase extraction: "without <something>", "not <something>"
    sentences = [s.strip() for s in text.replace("\n", ".").split(".") if s.strip()]
    for sentence in sentences:
        s_lower = sentence.lower()
        if "without " in s_lower or "not performed" in s_lower or "not verified" in s_lower or "lacking " in s_lower:
            # Avoid duplicate general entries
            if sentence not in failures and len(sentence) <= 120:
                failures.append(sentence)

    # Deduplicate while keeping order
    seen = set()
    deduped = []
    for item in failures:
        if item.lower() not in seen:
            seen.add(item.lower())
            deduped.append(item)

    return deduped if deduped else ["None detected"]

