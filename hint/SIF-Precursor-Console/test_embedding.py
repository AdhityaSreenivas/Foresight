from core.ml.embed import get_embedding


text = """
Worker entered the process tank without confirming
isolation. Gas monitor was not worn before entry.
"""

embedding = get_embedding(text)

print("Embedding size:", len(embedding))
print("First 10 values:", embedding[:10])