from core.ml.lsr import map_life_saving_rule


test_cases = [

    """
    Worker entered a confined space without gas monitoring.
    """,

    """
    Maintenance started without confirming equipment isolation.
    """,

    """
    Worker performed welding without proper hot work controls.
    """,

    """
    A suspended load passed over workers in the work area.
    """,

    """
    Worker climbed an elevated platform without a harness.
    """,

    """
    Crane lifting operation was performed without proper rigging.
    """,

    """
    Driver was operating a vehicle at excessive speed without a seatbelt.
    """,

    """
    Operator bypassed a safety alarm to continue production.
    """
]


for index, text in enumerate(test_cases, 1):

    result = map_life_saving_rule(text)

    print("\n" + "=" * 60)
    print(f"TEST {index}")
    print("=" * 60)

    print("Rule:", result["rule"])
    print("Score:", result["score"])
    print("Matched keywords:", result["matched_keywords"])