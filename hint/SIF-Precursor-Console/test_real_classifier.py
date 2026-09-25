from core.ml.classify import classify_report


test_reports = [

    """
    Worker entered a confined space tank without confirming
    isolation of the inlet valve. Gas monitor was not worn.
    Supervisor was not informed before entry.
    """,

    """
    Housekeeping activity completed in the office area.
    Floor was clean and no hazards were observed.
    """,

    """
    During maintenance, electrical equipment was worked on
    without proper lockout and isolation.
    """,

    """
    Worker climbed a scaffold at height without wearing
    fall protection harness.
    """
]


for i, text in enumerate(test_reports, 1):

    print("\n" + "=" * 60)
    print(f"REPORT {i}")
    print("=" * 60)

    print(text.strip())

    result = classify_report(text)

    print("\nMODEL RESULT:")
    print("Classification:", result["classification"])
    print("Is SIF:", result["is_sif"])
    print("Confidence:", result["confidence"])