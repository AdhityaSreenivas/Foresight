import json
from pathlib import Path

from core.ml.embed import get_embedding


PROJECT_ROOT = Path(__file__).resolve().parent

DATASET_PATH = (
    PROJECT_ROOT
    / "data"
    / "training_data.jsonl"
)

with open(
    DATASET_PATH,
    "r",
    encoding="utf-8"
) as file:

    data = [
        json.loads(line)
        for line in file
        if line.strip()
    ]


texts = [
    item["report_text"]
    for item in data
    if item.get("report_text")
]


print("Total texts:", len(texts))

print("\nTesting embeddings...")


for index, text in enumerate(texts[:1000]):

    embedding = get_embedding(text)

    print(
        f"Processed {index + 1}/1000 | "
        f"Embedding shape: {embedding.shape}"
    )


print("\n100 embeddings completed successfully.")