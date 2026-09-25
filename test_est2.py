import pandas as pd
from apps.datasets.parsers import estimate_row_count
import csv

# Quoted newlines
with open("test_quoted.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["col1", "col2"])
    for i in range(23):
        writer.writerow([f"data{i}", "test"])
    writer.writerow(["data\nwith\nnewlines", "test"])

est = estimate_row_count("test_quoted.csv", "csv")
df = pd.read_csv("test_quoted.csv")
actual = len(df)
print(f"Quoted newlines: estimate={est}, actual={actual}")
