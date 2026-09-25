import pandas as pd
import time

print("measuring pandas dict conversion...")
t0 = time.time()
count = 0
for chunk in pd.read_csv("scratch/big.csv", chunksize=100000, on_bad_lines="skip", dtype=str, keep_default_na=False):
    # Just counting length is fast. What if we do dict conversion?
    rows = chunk.where(chunk.notna(), other=None).to_dict(orient="records")
    count += len(rows)
t1 = time.time()
print(f"Counted {count} rows in {t1-t0:.2f} seconds")

