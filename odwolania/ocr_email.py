"""Adres kontaktowy bywa czytelny w oznaczonej rubryce pomimo utraty @ przez OCR."""

import re

from presidio_analyzer import EntityRecognizer, RecognizerResult


EMAIL_FIELD = re.compile(r"\b(?:e[-‐‑ ]?mail|mail)[ \t]*:[ \t]*(?=([^\r\n\f,;]+))", re.I)
NEXT_FIELD = re.compile(
    r"\s+[|•·]\s+|\s+(?:[|/*•·–—-]\s*)?(?=(?:tel(?:efon)?\.?\s*[:+\d]|faks\b|fax\b|"
    r"(?:e-?mail|adres|kontakt|strona|PESEL|NIP|REGON|KRS)\s*:|www[. ]|https?://))", re.I,
)
VALID_EMAIL = re.compile(r"[\w.%+-]+@(?:[\w-]+\.)+[\w-]{2,}\b")
DOMAIN_END = re.compile(r"[\w-]\.[^\W\d_]{2,}(?:[ \t]+[^\W\d_]{1,3}){0,2}$")
BROKEN_DOMAIN = re.compile(r"[\w.][(@©GOQ][\w|(/%-]*-[\w-]+ [^\W\d_]{2,8}$")


class LabelledEmailRecognizer(EntityRecognizer):
    def __init__(self):
        super().__init__(supported_entities=["PL_EMAIL"], supported_language="pl")

    def load(self):
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        damaged = set()
        for match in EMAIL_FIELD.finditer(text):
            value = NEXT_FIELD.split(match[1], maxsplit=1)[0].strip().rstrip(".").rstrip()
            if (not VALID_EMAIL.match(value)
                    and (DOMAIN_END.search(value) or BROKEN_DOMAIN.search(value))):
                damaged.add(value)
        if not damaged:
            return []
        # Uwzględnij także identyczny zapis w stopce lub treści, gdzie pominięto etykietę.
        values = "|".join(re.escape(value) for value in sorted(damaged, key=len, reverse=True))
        return [
            RecognizerResult("PL_EMAIL", match.start(), match.end(), 1.0)
            for match in re.finditer(r"(?<!\w)(?:" + values + r")(?!\w)", text)
        ]
