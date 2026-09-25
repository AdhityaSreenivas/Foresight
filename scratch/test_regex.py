import re
BODY_PART_PATTERNS = {
    "eye": re.compile(r"\b(eye injury|injured (?:his|her|their)?\s*eye|injury to (?:the\s+)?eye)\b", re.IGNORECASE),
}
text = "Worker experienced a serious eye injury from chemical splash."
print(bool(BODY_PART_PATTERNS["eye"].search(text)))
