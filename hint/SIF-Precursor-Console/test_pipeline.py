from core.ml.pipeline import analyze_report


text = """
During maintenance activity, a worker entered a confined space
without completing gas testing. The equipment isolation was not
verified before entry. The worker was exposed to potentially
hazardous atmospheric conditions.
"""


result = analyze_report(text)


print("=" * 60)
print("SIF PRECURSOR ANALYSIS")
print("=" * 60)


classification = result["classification"]

print("\nCLASSIFICATION")
print("----------------")

print(
    classification["classification"]
)

print(
    "Confidence:",
    round(
        classification["confidence"],
        3
    )
)


print("\nRISK LEVEL")
print("----------------")

print(
    result["risk_level"]
)


print("\nLIFE-SAVING RULE")
print("----------------")

print(
    result["lsr"]["rule"]
)

print(
    "Matched:",
    result["lsr"]["matched_keywords"]
)


print("\nPRECURSORS")
print("----------------")

for precursor in result["precursors"]:

    print(
        f"• {precursor['name']}"
    )

    print(
        f"  Severity: {precursor['severity']}"
    )


print("\nEVIDENCE")
print("----------------")

for item in result["evidence"]:

    print(
        f"\n{item['precursor']}:"
    )

    for sentence in item["evidence"]:

        print(
            f"  → {sentence}"
        )