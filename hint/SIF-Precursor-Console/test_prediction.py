from core.ml.classify import classify_report


text = """
Worker entered the process tank without confirming isolation.
Gas monitor was not worn before entry.
Supervisor was not informed before entry.
"""


result = classify_report(text)

print("\nPrediction:")
print(result)