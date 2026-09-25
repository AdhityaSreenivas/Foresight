from core.ml.classify import classify_report


text = """
During maintenance activity, a worker entered a confined space
without completing gas testing. The equipment isolation was not
verified before entry and the worker was exposed to potentially
hazardous atmospheric conditions.
"""


result = classify_report(text)

print("=" * 60)
print("SIF CLASSIFICATION RESULT")
print("=" * 60)

print("Classification:", result["classification"])
print("Is SIF:", result["is_sif"])
print("Confidence:", result["confidence"])