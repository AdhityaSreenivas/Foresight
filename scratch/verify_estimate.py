from apps.datasets.parsers import estimate_row_count
import pandas as pd

def test_file(content: bytes):
    with open("scratch/temp.csv", "wb") as f:
        f.write(content)
    
    est = estimate_row_count("scratch/temp.csv", "csv")
    
    # how pandas reads it:
    df = pd.read_csv("scratch/temp.csv")
    actual = len(df)
    print(f"est: {est}, actual: {actual}")

test_file(b"h1,h2\n1,2\n3,4\n")
test_file(b"h1,h2\n1,2\n3,4")
test_file(b"h1,h2\r1,2\r3,4\r")
test_file(b"h1,h2\n1,2\n3,4\r")
