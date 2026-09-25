from core.ml.precursor import detect_precursors
from core.ml.evidence import extract_evidence


text = """
During maintenance activity, a worker entered a confined space
without completing gas testing. The equipment isolation was not
verified before entry. The worker was exposed to potentially
hazardous atmospheric conditions.
"""


precursors = detect_precursors(text)

evidence = extract_evidence(
    text,
    precursors
)


print("=" * 60)
print("EVIDENCE EXTRACTION")
print("=" * 60)


for item in evidence:

    print("\nPrecursor:")
    print(item["precursor"])

    print("Evidence:")

    for sentence in item["evidence"]:

        print(
            "  →",
            sentence
        )