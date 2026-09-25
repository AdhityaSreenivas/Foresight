import re


def clean_text(text):

    if not text:
        return ""

    text = text.strip()

    # Remove excessive whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text