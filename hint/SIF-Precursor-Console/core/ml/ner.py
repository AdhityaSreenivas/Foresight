BARRIER_FAILURES = [

    "not isolated",
    "no isolation",
    "without isolation",
    "no permit",
    "permit not obtained",
    "not worn",
    "no gas monitor",
    "no barricade",
    "not barricaded",
    "not informed",
    "not confirmed",
    "bypass",
    "override",
    "disabled alarm",
    "no supervision",
    "unattended",

]


def extract_barrier_failures(text):

    text_lower = text.lower()

    found = []

    for phrase in BARRIER_FAILURES:

        if phrase in text_lower:

            found.append(
                phrase
            )

    return found[:5]
ACTIVITIES = {

    "Confined Space Entry": [
        "confined space",
        "tank",
        "vessel",
    ],

    "Hot Work": [
        "welding",
        "weld",
        "grinding",
        "hot work",
    ],

    "Lifting Operation": [
        "crane",
        "lifting",
        "sling",
        "hoist",
    ],

    "Working at Height": [
        "scaffold",
        "ladder",
        "height",
        "harness",
    ],

    "Vehicle Movement": [
        "vehicle",
        "truck",
        "driving",
        "forklift",
    ],

    "Energy Isolation": [
        "isolation",
        "loto",
        "lockout",
    ],
}


def extract_activity(text):

    text = text.lower()

    best_activity = "Other"
    best_score = 0

    for activity, keywords in ACTIVITIES.items():

        score = sum(
            keyword in text
            for keyword in keywords
        )

        if score > best_score:

            best_score = score
            best_activity = activity

    return best_activity