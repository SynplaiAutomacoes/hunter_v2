from __future__ import annotations

import re
import unicodedata

PORTUGUESE_PARTICLES = {
    "da",
    "de",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "o",
    "a",
    "os",
    "as",
    "no",
    "na",
    "nos",
    "nas",
    "ao",
    "aos",
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_REGEX = re.compile(r"(https?://\S+|www\.\S+)")
FILENAME_REGEX = re.compile(r"\b[^/\\]+\.(?:pdf|docx?|xlsx?|jpe?g|png|gif|txt|csv)\b", re.IGNORECASE)
UUID_REGEX = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
ALPHANUMERIC_CODE_REGEX = re.compile(r"(?i)^(?=.*[a-z])(?=.*\d)[a-z0-9\-_/]{4,}$")
NUMERIC_REGEX = re.compile(r"^[0-9.,\-]+$")
PLATE_REGEX = re.compile(r"^[A-Z]{3}-?\d[A-Z0-9]\d{2}$", re.IGNORECASE)
WORD_REGEX = re.compile(r"\b[\wÀ-ÿ'-]+\b", re.UNICODE)


def _strip_accents(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("utf-8")


def _normalize_token(token: str) -> str:
    cleaned = token.strip("'\"()[]{}<>.,;:!?\n\r\t")
    return _strip_accents(cleaned).lower()


def _is_excluded_token(token: str) -> bool:
    if not token:
        return False

    normalized = _normalize_token(token)
    if not normalized:
        return False

    if EMAIL_REGEX.search(normalized):
        return True
    if URL_REGEX.search(normalized):
        return True
    if FILENAME_REGEX.search(normalized):
        return True
    if UUID_REGEX.search(normalized):
        return True
    if NUMERIC_REGEX.match(normalized):
        return True
    if PLATE_REGEX.match(normalized.upper()):
        return True
    if ALPHANUMERIC_CODE_REGEX.match(normalized):
        return True

    return False


def _capitalize_word(word: str) -> str:
    if not word:
        return word

    lower = word.lower()
    for index, char in enumerate(lower):
        if char.isalpha():
            return lower[:index] + char.upper() + lower[index + 1 :]
    return lower


def _should_preserve_upper_token(token: str) -> bool:
    stripped = token.strip()
    if len(stripped) < 2:
        return False
    if stripped != stripped.upper():
        return False

    alpha_count = sum(char.isalpha() for char in stripped)
    if alpha_count < 2:
        return False

    return bool(re.fullmatch(r"[A-Z0-9À-Ý'\-/]+", stripped))


def _title_case_word(word: str) -> str:
    if not word:
        return word

    parts = re.split(r"([\-'])", word)
    result_parts: list[str] = []
    for part in parts:
        if part in {"-", "'"}:
            result_parts.append(part)
        else:
            result_parts.append(_capitalize_word(part))
    return "".join(result_parts)


def sentence_case(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text

    sentence_parts = re.split(r"([.!?]+\s*)", text)
    output: list[str] = []

    for index in range(0, len(sentence_parts), 2):
        segment = sentence_parts[index]
        delimiter = sentence_parts[index + 1] if index + 1 < len(sentence_parts) else ""

        if not segment:
            output.append(segment)
            output.append(delimiter)
            continue

        tokens = re.split(r"(\b[\wÀ-ÿ'-]+\b)", segment, flags=re.UNICODE)
        first_word = True
        segment_output: list[str] = []
        for token in tokens:
            if not token:
                continue
            if WORD_REGEX.fullmatch(token):
                if _is_excluded_token(token) or _should_preserve_upper_token(token):
                    segment_output.append(token)
                else:
                    if first_word:
                        segment_output.append(_capitalize_word(token))
                        first_word = False
                    else:
                        segment_output.append(token.lower())
            else:
                segment_output.append(token)
        output.append("".join(segment_output))
        output.append(delimiter)

    return "".join(output).strip()


def name_case(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text

    tokens = re.split(r"(\b[\wÀ-ÿ'-]+\b)", text, flags=re.UNICODE)
    output: list[str] = []
    first_word = True

    for token in tokens:
        if not token:
            continue
        if WORD_REGEX.fullmatch(token):
            if _is_excluded_token(token):
                output.append(token)
                first_word = False
                continue

            normalized = _normalize_token(token)
            if not first_word and normalized in PORTUGUESE_PARTICLES:
                output.append(token.lower())
            else:
                output.append(_title_case_word(token))
            first_word = False
        else:
            output.append(token)
            if any(mark in token for mark in (".", "!", "?")):
                first_word = True

    return "".join(output).strip()


def plate_case(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text

    return text.strip().upper()
