import csv
import io
from pathlib import Path
from docx import Document
from pypdf import PdfReader


ALLOWED_EXTENSIONS = {".txt", ".csv", ".docx", ".pdf"}


def extract_text_from_file(uploaded_file):
    """
    Extract report text from a supported uploaded file.

    Returns:
        list[str]: Extracted report texts.
    """

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}. "
            f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if extension == ".txt":
        return extract_txt(uploaded_file)

    if extension == ".csv":
        return extract_csv(uploaded_file)

    if extension == ".docx":
        return extract_docx(uploaded_file)

    if extension == ".pdf":
        return extract_pdf(uploaded_file)

    return []


def extract_txt(uploaded_file):
    """
    Extract one report per non-empty line from a TXT file.
    Handles UTF-8, UTF-8 BOM, UTF-16 and common Indian/Windows encodings.
    """

    raw = uploaded_file.read()

    if not raw:
        return []

    encodings = [
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1252",
        "latin-1",
    ]

    content = None

    for encoding in encodings:
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        raise ValueError("Could not decode the TXT file.")

    reports = []

    for line in content.splitlines():
        line = line.strip()

        if line:
            reports.append(line)

    return reports

def extract_csv(uploaded_file):
    """
    Extract reports from CSV.

    Expected report column can be:
    - report_text
    - description
    - report
    - text
    """

    content = uploaded_file.read().decode(
        "utf-8-sig",
        errors="ignore"
    )

    reader = csv.DictReader(
        io.StringIO(content)
    )

    reports = []

    for row in reader:

        text = (
            row.get("report_text")
            or row.get("description")
            or row.get("report")
            or row.get("text")
            or ""
        )

        text = text.strip()

        if text:
            reports.append(text)

    return reports


def extract_docx(uploaded_file):
    """Extract each non-empty DOCX paragraph as one report."""

    document = Document(uploaded_file)

    reports = []

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:
            reports.append(text)

    return reports


def extract_pdf(uploaded_file):
    """
    Extract text from text-based PDF files.

    Each page is returned as one report block.
    """

    reader = PdfReader(uploaded_file)

    reports = []

    for page in reader.pages:

        text = page.extract_text() or ""

        text = text.strip()

        if text:
            reports.append(text)

    return reports