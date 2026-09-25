import pandas as pd
from apps.datasets.parsers import estimate_row_count

# create a csv with 24 data rows and 1 header
import csv
with open("test_24.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["col1", "col2"])
    for i in range(24):
        writer.writerow([f"data{i}", "test"])

est = estimate_row_count("test_24.csv", "csv")
df = pd.read_csv("test_24.csv")
actual = len(df)
print(f"Normal CSV: estimate={est}, actual={actual}")

# what if it has trailing blank line?
with open("test_24_trailing.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["col1", "col2"])
    for i in range(24):
        writer.writerow([f"data{i}", "test"])
    f.write("\n")

est2 = estimate_row_count("test_24_trailing.csv", "csv")
df2 = pd.read_csv("test_24_trailing.csv")
actual2 = len(df2)
print(f"Trailing blank: estimate={est2}, actual={actual2}")

# what if it doesn't end with newline?
with open("test_24_no_newline.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["col1", "col2"])
    for i in range(23):
        writer.writerow([f"data{i}", "test"])
    f.write("data23,test")

est3 = estimate_row_count("test_24_no_newline.csv", "csv")
df3 = pd.read_csv("test_24_no_newline.csv")
actual3 = len(df3)
print(f"No trailing newline: estimate={est3}, actual={actual3}")
