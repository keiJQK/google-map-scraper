import re


def normalize_language(language: str) -> str:
    """To validate a single language tag and normalize its language, script, and region casing."""

    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language.strip()):
        raise ValueError("language must be a single language code such as en, ja, or pt-BR; see references/languages.md")
    parts = language.strip().split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.title() if len(part) == 4 and part.isalpha() else part.upper() if len(part) == 2 else part.lower())
    return "-".join(normalized)
