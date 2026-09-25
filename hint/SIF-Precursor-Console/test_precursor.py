from core.ml.precursor import detect_precursors


text = """
During maintenance activity, a worker entered a confined space
without completing gas testing. The equipment isolation was not
verified before entry.
"""


results = detect_precursors(text)


print("=" * 60)
print("SIF PRECURSOR DETECTION")
print("=" * 60)


for precursor in results:

    print("\nPrecursor:", precursor["name"])
    print("Severity:", precursor["severity"])
    print("Matched:", precursor["matched_keywords"])