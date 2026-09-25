import re
import logging

logger = logging.getLogger(__name__)

# Canonical representation of the 9 IOGP Life-Saving Rules
IOGP_RULES = {
    "Bypassing Safety Controls": {
        "description": "Obtain authorisation before overriding or disabling safety controls",
        "keywords": [
            r"bypass(?:ing|ed)?", r"override", r"disabl[a-z]*", r"interlock",
            r"jumper[a-z]*", r"defeat[a-z]*", r"safety control", r"alarm silenc[a-z]*",
            r"guard removed", r"safety device removed"
        ]
    },
    "Confined Space": {
        "description": "Obtain authorisation before entering a confined space",
        "keywords": [
            r"confined space", r"vessel entry", r"tank entry", r"manhole",
            r"permit to enter", r"atmospheric test", r"gas test[a-z]*",
            r"oxygen level", r"o2 level", r"ventilation", r"enclosed space",
            r"entry permit"
        ]
    },
    "Driving": {
        "description": "Follow safe driving rules",
        "keywords": [
            r"vehicle", r"driving", r"drove", r"driver", r"seatbelt", r"seat belt",
            r"road", r"collision", r"speeding", r"mobile phone while driving",
            r"fatigue driving", r"rollover", r"skid"
        ]
    },
    "Energy Isolation": {
        "description": "Verify isolation and zero energy before work begins",
        "keywords": [
            r"loto", r"lockout", r"tag out", r"tagout", r"isolat[a-z]*",
            r"de-energ[a-z]*", r"lock and tag", r"test for dead", r"zero energy",
            r"breaker", r"bleed", r"depressurize"
        ]
    },
    "Hot Work": {
        "description": "Control flammables and ignition sources",
        "keywords": [
            r"hot work", r"welding", r"cutting", r"grinding", r"sparks",
            r"ignition source", r"burn[a-z]*", r"torch", r"hot permit",
            r"fire watch", r"combustible", r"flammable"
        ]
    },
    "Line of Fire": {
        "description": "Keep yourself and others out of the line of fire",
        "keywords": [
            r"line of fire", r"struck by", r"falling object", r"dropped object",
            r"pinch point", r"crushed", r"caught between", r"tension",
            r"pressure release", r"swing radius", r"barricade", r"exclusion zone"
        ]
    },
    "Safe Mechanical Lifting": {
        "description": "Plan lifting operations and control the area",
        "keywords": [
            r"lift[a-z]*", r"crane", r"hoist", r"rigging", r"sling",
            r"suspended load", r"tag line", r"rigger", r"swl",
            r"safe working load", r"drop[a-z]*", r"overhead load"
        ]
    },
    "Work Authorization": {
        "description": "Work with a valid permit when required",
        "keywords": [
            r"permit to work", r"ptw", r"jsa", r"jha", r"job safety analysis",
            r"risk assessment", r"clearance", r"authorization", r"safety briefing",
            r"tool box talk", r"toolbox"
        ]
    },
    "Working at Height": {
        "description": "Protect yourself against a fall when working at height",
        "keywords": [
            r"height", r"fall", r"harness", r"lanyard", r"tie-off",
            r"scaffolding", r"scaffold", r"edge protection", r"lifeline",
            r"mewp", r"cherry picker", r"dropped from height"
        ]
    }
}

# Compile the regexes for performance, adding word boundaries to prevent trivial sub-word matching
COMPILED_RULES = {}
for rule_name, data in IOGP_RULES.items():
    compiled_patterns = []
    for kw in data["keywords"]:
        pattern = rf"\b{kw}\b"
        compiled_patterns.append((kw, re.compile(pattern, re.IGNORECASE)))
    COMPILED_RULES[rule_name] = compiled_patterns

# Safety control / authorization terms: when preceded by 'without', these indicate
# an unprotected hazard / breach of control, NOT a negation of the activity.
CONTROL_TERMS = {
    "permit", "ptw", "authorization", "authorisation", "clearance", "jsa", "jha",
    "permit to work", "permit to enter", "entry permit", "hot permit",
    "harness", "lanyard", "tie-off", "lifeline", "scaffolding", "scaffold", "edge protection",
    "loto", "lockout", "tagout", "tag out", "isolation", "breaker",
    "gas test", "atmospheric test", "ventilation", "fire watch",
    "guard", "safety device", "interlock", "seatbelt", "seat belt", "barricade",
    "exclusion zone", "swl", "safe working load"
}

# Regex for negation preceding a keyword match (within ~60 chars in the same clause)
PRECEDING_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|neither|nor)\b(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE
)

# Regex for 'without' preceding an activity (e.g., 'without entering', 'without lifting')
PRECEDING_WITHOUT_ACTIVITY_RE = re.compile(
    r"\bwithout\s+(?:any\s+)?(?:actual\s+)?(?:entering|performing|doing|undertaking|conducting|operating|using|involving|carrying\s+out)\s*$",
    re.IGNORECASE
)

# Regex for following negation phrases (e.g., 'was not performed', 'did not occur')
FOLLOWING_NEGATION_RE = re.compile(
    r"^\s*(?:operation|activity|work|entry|event)?\s*(?:was|were|is|are|been|being|did)?\s*(?:not|never)\s+(?:performed|conducted|undertaken|carried\s+out|involved|permitted|occurred|done|observed|take\s+place)\b",
    re.IGNORECASE
)

# Regex for incidental storage/parked/idle mentions
INCIDENTAL_CONTEXT_RE = re.compile(
    r"\b(?:stored|parked|kept|idle|inactive|unrelated|passed\s+by|adjacent\s+to|located\s+near|stationed\s+near|lying\s+on\s+the\s+ground|in\s+storage)\b",
    re.IGNORECASE
)

FOLLOWING_INCIDENTAL_RE = re.compile(
    r"^\s*(?:machine|equipment|vehicle|crane|material|tools?)?\s*(?:was|were|is|are)?\s*(?:stored|parked|kept|idle|inactive|located|stationed)\s+(?:nearby|in\s+the\s+area|in\s+storage|adjacent|away\s+from|on\s+site)\b",
    re.IGNORECASE
)

# Regex for post-incident corrective action context
POST_INCIDENT_ADMIN_RE = re.compile(
    r"\b(?:revised|updated|conducted|reviewed|organized|briefed|retrained|discussed|re-issued)\s+(?:after|post|following)\s+(?:the\s+)?(?:incident|event|accident)\b"
    r"|\b(?:after|post|following)\s+(?:the\s+)?(?:incident|event|accident)[,\s]+(?:a\s+)?(?:revised|updated|conducted|reviewed|new|briefing)\b"
    r"|\b(?:as\s+a\s+corrective\s+action|corrective\s+action|action\s+item|lesson\s+learned)\b",
    re.IGNORECASE
)


def _check_match_context(text: str, start: int, end: int, field_name: str, keyword: str) -> tuple[bool, str]:
    """
    Evaluates the surrounding context of a keyword match in text.
    
    Returns:
        (is_negated: bool, match_type: str)
        match_type is one of: "direct_event", "corrective_action", "incidental"
    """
    # Extract preceding clause up to 60 chars before start (bounded by sentence punctuation)
    preceding_raw = text[max(0, start - 60):start]
    preceding_clause = re.split(r"[\.\?!;\n]", preceding_raw)[-1]

    # Extract following clause up to 60 chars after end
    following_raw = text[end:min(len(text), end + 60)]
    following_clause = re.split(r"[\.\?!;\n]", following_raw)[0]

    # 1. Check for following negation (e.g. "lifting operation was not performed")
    if FOLLOWING_NEGATION_RE.search(following_clause):
        return True, "negated"

    # 2. Check for preceding negation
    if PRECEDING_NEGATION_RE.search(preceding_clause):
        return True, "negated"

    # 3. Check for 'without' preceding an activity verb
    if PRECEDING_WITHOUT_ACTIVITY_RE.search(preceding_clause):
        return True, "negated"

    # 4. Check for 'without' directly preceding a non-control keyword
    # e.g., "without hot work", "without confined space entry"
    without_match = re.search(r"\bwithout\s+(?:any\s+)?$", preceding_clause, re.IGNORECASE)
    if without_match and keyword.lower() not in CONTROL_TERMS:
        return True, "negated"

    # 4b. Oil & Gas domain distinction: "cold cutting" is non-hot work (explicit avoidance of hot work)
    if keyword.lower() == "cutting" and re.search(r"\bcold\s*$", preceding_clause, re.IGNORECASE):
        return True, "negated"

    # 5. Check for post-incident corrective action mentions
    surrounding_snippet = f"{preceding_clause} {text[start:end]} {following_clause}"
    if field_name in ("corrective_actions", "remedial_actions") or POST_INCIDENT_ADMIN_RE.search(surrounding_snippet):
        return False, "corrective_action"

    # 6. Check for incidental mentions (stored nearby, parked, idle)
    if INCIDENTAL_CONTEXT_RE.search(preceding_clause) or FOLLOWING_INCIDENTAL_RE.search(following_clause):
        return False, "incidental"

    return False, "direct_event"


def classify_iogp_rules(fields_dict: dict) -> list[dict]:
    """
    Deterministic rule-based classification against IOGP Life-Saving Rules
    with semantic hardening: conservative negation filtering, context differentiation
    (direct event vs incidental vs corrective action), and honest match_strength scoring.
    
    Args:
        fields_dict: A dictionary of text fields to check (e.g., description, job_task, corrective_actions).
                     Excludes severity fields!
                     
    Returns:
        List of dicts containing match information:
        [
            {
                "rule": "Confined Space",
                "matched_keywords": ["confined space", "permit to enter"],
                "matched_fields": ["description", "job_task"],
                "match_strength": 1.0,
                "confidence": 1.0,
                "match_type": "direct_event",
                "classification_method": "rule_based_contextual",
                "classifier_version": "iogp_rules_v2"
            }
        ]
    """
    matches = {}
    
    # Check each field
    for field_name, text in fields_dict.items():
        if not text:
            continue
            
        text = str(text)
        
        for rule_name, patterns in COMPILED_RULES.items():
            for kw, pattern in patterns:
                for match in pattern.finditer(text):
                    is_negated, match_type = _check_match_context(
                        text, match.start(), match.end(), field_name, kw
                    )
                    
                    # If negated, ignore this occurrence completely
                    if is_negated:
                        logger.debug(
                            "Negated IOGP match ignored: rule=%s, kw=%s, field=%s",
                            rule_name, kw, field_name
                        )
                        continue

                    if rule_name not in matches:
                        matches[rule_name] = {
                            "matched_keywords": set(),
                            "matched_fields": set(),
                            "match_types": set(),
                        }
                    matches[rule_name]["matched_keywords"].add(match.group(0).lower())
                    matches[rule_name]["matched_fields"].add(field_name)
                    matches[rule_name]["match_types"].add(match_type)

    # Format output
    results = []
    for rule_name, match_data in matches.items():
        match_types = match_data["match_types"]

        # Determine dominant match type and calibrate honest match strength
        if "direct_event" in match_types:
            overall_type = "direct_event"
            match_strength = 1.0
        elif "corrective_action" in match_types:
            overall_type = "corrective_action"
            match_strength = 0.5
        elif "incidental" in match_types:
            overall_type = "incidental"
            match_strength = 0.3
        else:
            overall_type = "direct_event"
            match_strength = 1.0

        results.append({
            "rule": rule_name,
            "matched_keywords": sorted(list(match_data["matched_keywords"])),
            "matched_fields": sorted(list(match_data["matched_fields"])),
            "match_strength": match_strength,
            "confidence": match_strength,  # Retained as alias for backward compatibility
            "match_type": overall_type,
            "classification_method": "rule_based_contextual",
            "classifier_version": "iogp_rules_v2"
        })
        
    return sorted(results, key=lambda x: x["rule"])
