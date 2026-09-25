import pandas as pd
from apps.datasets.parsers import estimate_row_count

with open("test_r.csv", "wb") as f:
    f.write(b"col1,col2\r") # header
    for i in range(24):
        f.write(f"data{i},test\r".encode())
    f.write(b"data24,test") # 25th data row, no newline

est = estimate_row_count("test_r.csv", "csv")
df = pd.read_csv("test_r.csv")
actual = len(df)
print(f"\\r only: estimate={est}, actual={actual}")

with open("test_mixed.csv", "wb") as f:
    f.write(b"col1,col2\n") # header
    for i in range(23):
        f.write(f"data{i},test\n".encode())
    f.write(b"data23,test\rdata24,test\n") 

est2 = estimate_row_count("test_mixed.csv", "csv")
df2 = pd.read_csv("test_mixed.csv")
actual2 = len(df2)
print(f"Mixed newlines: estimate={est2}, actual={actual2}")
