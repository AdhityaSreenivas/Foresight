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
    ],

    "Confined Space": [
        "confined",
        "tank",
        "vessel",
        "enclosed",
        "gas monitor",
        "entry permit",
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
        "struck by",
        "dropped object",
        "overhead",
    ],

    "Working at Height": [
        "height",
        "scaffold",
        "fall",
        "harness",
        "ladder",
        "elevated",
    ],

    "Lifting Operations": [
        "crane",
        "lifting",
        "load",
        "sling",
        "rigger",
        "hoist",
    ],

    "Driving": [
        "vehicle",
        "driving",
        "speed",
        "seatbelt",
        "road",
        "truck",
    ],

    "Bypassing Safety Controls": [
        "bypass",
        "override",
        "disabled alarm",
        "defeat",
        "by-passed",
    ],
}


def map_life_saving_rule(text):

    text_lower = text.lower()

    best_rule = "Unclassified"
    best_score = 0
    matched_keywords = []

    for rule, keywords in LSR_RULES.items():

        matches = [
            keyword
            for keyword in keywords
            if keyword in text_lower
        ]

        score = len(matches)

        if score > best_score:

            best_score = score
            best_rule = rule
            matched_keywords = matches

    return {
        "rule": best_rule,
        "score": best_score,
        "matched_keywords": matched_keywords,
    }