import pandas as pd
import io

csv_data = b"h1,h2\n1,2\n3,4\n\n\n5,6\n"
df = pd.read_csv(io.BytesIO(csv_data), on_bad_lines="skip")
print(f"Data rows: {len(df)}")
