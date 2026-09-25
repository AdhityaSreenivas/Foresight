import tempfile
import json
from pathlib import Path
import pytest
import pandas as pd

from apps.datasets.parsers import (
    detect_file_type,
    detect_encoding,
    estimate_row_count,
    infer_column_types,
    parse_preview,
    iter_file_chunks,
)


def test_detect_file_type():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as f:
        f.write(b"col1,col2\n1,2")
        f_path = Path(f.name)
    assert detect_file_type(f_path, "csv") == "csv"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        f.write(b'[{"a": 1}]')
        f_path_json = Path(f.name)
    assert detect_file_type(f_path_json, "json") == "json"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as f:
        f.write(b'{"a": 1}\n{"b": 2}')
        f_path_jsonl = Path(f.name)
    assert detect_file_type(f_path_jsonl, "jsonl") == "jsonl"

    f_path.unlink()
    f_path_json.unlink()
    f_path_jsonl.unlink()


def test_detect_file_type_mismatch():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        # Content is CSV, but extension is JSON
        f.write(b"col1,col2\n1,2")
        f_path = Path(f.name)

    with pytest.raises(ValueError, match="does not look like JSON"):
        detect_file_type(f_path, "json")

    f_path.unlink()


def test_estimate_row_count():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as f:
        f.write(b"col1,col2\n1,2\n3,4\n5,6\n")
        f_path = Path(f.name)

    assert estimate_row_count(f_path, "csv") == 3
    f_path.unlink()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        f.write(b'[{"a":1},{"b":2}]')
        f_path_json = Path(f.name)

    assert estimate_row_count(f_path_json, "json") == 2
    f_path_json.unlink()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as f:
        f.write(b'{"a":1}\n{"b":2}\n{"c":3}\n')
        f_path_jsonl = Path(f.name)

    assert estimate_row_count(f_path_jsonl, "jsonl") == 3
    f_path_jsonl.unlink()


def test_csv_missing_fields_and_blank_rows():
    content = (
        "col1,col2,col3\n"
        "1,2,3\n"
        "\n"
        "1,,3\n"
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert len(preview.preview_rows) == 2  # skipped blank row
    assert preview.columns == ["col1", "col2", "col3"]
    assert preview.preview_rows[1]["col2"] == "" or preview.preview_rows[1]["col2"] is None

    f_path.unlink()


def test_csv_trailing_commas_and_quotes():
    content = (
        'id,description,notes,\n'
        '101,"Worker slipped on oil, near miss",none,\n'
        '102,"Conveyor belt jammed; \\"urgent fix\\"",action pending,\n'
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert len(preview.preview_rows) == 2
    assert "description" in preview.columns
    assert "Worker slipped on oil" in preview.preview_rows[0]["description"]

    chunks = list(iter_file_chunks(f_path, "csv"))
    assert len(chunks) == 1
    rows, skipped = chunks[0]
    assert len(rows) == 2
    assert skipped == 0

    f_path.unlink()


def test_csv_encodings_latin1_and_windows1252():
    # Write a file in latin-1 with accented characters
    content = "id,département,détails\n1,Sécurité,Chute d'échelle\n2,Entrepôt,Échafaudage\n"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="wb") as f:
        f.write(content.encode("latin-1"))
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert len(preview.preview_rows) == 2
    assert "département" in preview.columns or "d\xe9partement" in preview.columns
    assert "Chute d'échelle" in str(preview.preview_rows[0]) or "Chute d" in str(preview.preview_rows[0])

    chunks = list(iter_file_chunks(f_path, "csv"))
    rows, skipped = chunks[0]
    assert len(rows) == 2

    f_path.unlink()


def test_csv_very_large_cell_value():
    large_narrative = "A" * 60_000
    content = f'id,narrative\n1,"{large_narrative}"\n'
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert len(preview.preview_rows) == 1
    assert len(preview.preview_rows[0]["narrative"]) == 60_000

    f_path.unlink()


def test_csv_html_js_payloads_as_inert_data():
    payload = '<script>alert("XSS")</script><img src=x onerror=alert(1)>'
    escaped_payload = payload.replace('"', '""')
    content = f'id,description\n1,"{escaped_payload}"\n'
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert preview.preview_rows[0]["description"] == payload

    f_path.unlink()


def test_json_array_preview_and_streaming():
    data = [
        {"id": 1, "department": "Welding", "desc": "Spark flew into visor"},
        {"id": 2, "department": "Logistics", "desc": "Forklift near miss"},
        {"id": 3, "department": "Chemical", "desc": "Minor acid splash, PPE held"},
    ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as f:
        json.dump(data, f)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "json")
    assert len(preview.preview_rows) == 3
    assert set(preview.columns) == {"id", "department", "desc"}
    assert preview.total_rows == 3

    chunks = list(iter_file_chunks(f_path, "json"))
    assert len(chunks) == 1
    rows, skipped = chunks[0]
    assert len(rows) == 3
    assert skipped == 0

    f_path.unlink()


def test_json_empty_array():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as f:
        f.write("[]")
        f_path = Path(f.name)

    preview = parse_preview(f_path, "json")
    assert len(preview.preview_rows) == 0
    assert preview.columns == []
    assert preview.total_rows == 0

    f_path.unlink()


def test_jsonl_preview_and_streaming_with_blank_lines():
    content = (
        '{"id": 10, "department": "Assembly", "desc": "Pinch point incident"}\n'
        '\n'
        '{"id": 20, "department": "Packaging", "desc": "Box fell from pallet"}\n'
        '   \n'
        '{"id": 30, "department": "Maintenance", "desc": "LOTO audit finding"}\n'
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    preview = parse_preview(f_path, "jsonl")
    assert len(preview.preview_rows) == 3
    assert set(preview.columns) == {"id", "department", "desc"}

    chunks = list(iter_file_chunks(f_path, "jsonl"))
    assert len(chunks) == 1
    rows, skipped = chunks[0]
    assert len(rows) == 3
    assert skipped == 0

    f_path.unlink()


def test_jsonl_malformed_lines():
    content = (
        '{"id": 1, "desc": "Valid line 1"}\n'
        'INVALID JSON LINE HERE\n'
        '{"id": 2, "desc": "Valid line 2"}\n'
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w", encoding="utf-8") as f:
        f.write(content)
        f_path = Path(f.name)

    # Preview skips bad line
    preview = parse_preview(f_path, "jsonl")
    assert len(preview.preview_rows) == 2

    # Streaming reports skipped bad line
    chunks = list(iter_file_chunks(f_path, "jsonl"))
    rows, skipped = chunks[0]
    assert len(rows) == 2
    assert skipped == 1

    f_path.unlink()


def test_infer_column_types():
    df = pd.DataFrame({
        "str_col": ["a", "b", "c"],
        "num_col": ["1", "2.5", "300"],
        "date_col": ["2025-01-01", "2025-02-15", "2025-03-30"],
        "bool_col": ["true", "false", "yes"],
    })
    types = infer_column_types(df)
    assert types["str_col"] == "string"
    assert types["num_col"] == "number"
    assert types["date_col"] == "date"
    assert types["bool_col"] == "boolean"


def test_parsed_preview_attributes_regression():
    """Regression test ensuring ParsedPreview exposes preview_rows and required fields."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8") as f:
        f.write("a,b\n1,2\n")
        f_path = Path(f.name)

    preview = parse_preview(f_path, "csv")
    assert hasattr(preview, "preview_rows")
    assert hasattr(preview, "columns")
    assert hasattr(preview, "column_types")
    assert hasattr(preview, "total_rows")
    assert hasattr(preview, "file_type")
    assert hasattr(preview, "encoding")

    f_path.unlink()
