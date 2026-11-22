"""Load JSONC document shapes, header rules, and field formatting."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .rules import Rule, load_rule


JSONC_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/')
TRAILING_COMMA = re.compile(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])')
DIRECTIVE = re.compile(r"//[ \t]*@(match|normalize|singleton)(?:[ \t]+(.*))?")
POLISH_KEY_LETTERS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
TED_ISSUE = re.compile(r"(\d{4})/S\d{1,3}-(\d{6,8})", re.IGNORECASE)
HYPHENS = str.maketrans("‐‑–", "---")
QUOTE_PAIRS = {"„": "”", "“": "”", '"': '"', "«": "»", "»": "«"}
HEADER_LINES = 50
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y")
POLISH_MONTHS = {
    name: number for number, name in enumerate(
        ("stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
         "lipca", "sierpnia", "września", "października", "listopada", "grudnia"),
        start=1,
    )
}

FieldPath = tuple[str, ...]
Formatter = Callable[[str], str]


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("JSON zawiera powtórzone klucze.")
    return result


def _invalid_constant(value):
    raise ValueError(f"Niedozwolona stała JSON: {value}")


def load_json(source):
    return json.loads(source, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def _remove_comment(match):
    return match[0] if match[0].startswith('"') else " "


def _normalize_ted(value):
    compact = "".join(value.split()).translate(HYPHENS)
    issue = TED_ISSUE.fullmatch(compact)
    return f"{issue[2]}-{issue[1]}" if issue else compact


def _normalize_date(value):
    text = value.strip()
    parts = text.lower().split()
    if len(parts) == 3 and parts[1] in POLISH_MONTHS:
        day, month, year = parts
        text = f"{day}.{POLISH_MONTHS[month]}.{year}"

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def _given_name_initial(value: str) -> str:
    text = normalize_spaces(value)
    first, _, rest = text.partition(" ")
    if (len(first) >= 3 and first.isalpha() and first.islower() and rest[:1].isupper()
            and first not in {"van", "von", "del", "radca", "adwokat", "mecenas", "pani", "pan"}):
        return first[:1].upper() + text[1:]
    return text


def _normalize_transfer_title(value: str) -> str:
    title = normalize_spaces(value)
    quoted = title.removesuffix(".").rstrip()
    if len(quoted) >= 2:
        closing = QUOTE_PAIRS.get(quoted[0])
        content = quoted[1:-1]
        if quoted[-1] == closing and closing not in content:
            return content.strip()
    return title


FORMATTERS: dict[str, Formatter] = {
    "bank-account": lambda value: "".join(value.split()),
    "compact-upper": lambda value: "".join(value.split()).upper(),
    "date-iso": _normalize_date,
    "digits": lambda value: re.sub(r"\D", "", value),
    "given-name-initial": _given_name_initial,
    "spaces": normalize_spaces,
    "ted": _normalize_ted,
    "transfer-title": _normalize_transfer_title,
}


def _field_at(shape, path):
    for part in path:
        if part == "*" and isinstance(shape, list) and shape:
            shape = shape[0]
        elif isinstance(shape, dict) and part in shape:
            shape = shape[part]
        else:
            raise ValueError(f"Nieznane pole wzorca: {'.'.join(path)}")
    return shape


def _register_singleton(shape, aliases, argument):
    parts = argument.split()
    if len(parts) != 2:
        raise ValueError("Dyrektywa @singleton wymaga ścieżki listy i klucza pojedynczego rekordu.")
    path, alias = parts[0].split("."), parts[1]
    parent = tuple(path[:-1])
    key = path[-1]
    siblings = _field_at(shape, parent)
    records = siblings.get(key) if isinstance(siblings, dict) else None
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise ValueError(f"Dyrektywa @singleton wymaga listy obiektów: {parts[0]}")
    by_key = aliases.setdefault(parent, {})
    names = [name.translate(POLISH_KEY_LETTERS) for name in (*siblings, *by_key.values())]
    if (key in by_key or names.count(key.translate(POLISH_KEY_LETTERS)) != 1
            or alias.translate(POLISH_KEY_LETTERS) in names):
        raise ValueError(f"Niejednoznaczna dyrektywa @singleton: {argument}")
    by_key[key] = alias


@dataclass(frozen=True)
class DocumentTemplate:
    name: str
    prompt: str
    shape: dict
    headers: tuple[re.Pattern, ...]
    formatters: dict[FieldPath, Formatter]
    rule: Rule | None = None
    singleton_aliases: dict[FieldPath, dict[str, str]] = field(default_factory=dict)

    def apply_rules(self, text: str, result: dict) -> None:
        if self.rule:
            try:
                self.rule(text, result)
            except Exception as error:
                raise ValueError(f"Błąd reguł {self.name}: {type(error).__name__}.") from error

    @classmethod
    def load(cls, path: Path):
        try:
            return cls.parse(path.stem, path.read_text(encoding="utf-8-sig"), load_rule(path.with_suffix(".py")))
        except (OSError, ValueError, re.PatternError) as error:
            raise ValueError(f"{path.name}: {error}") from error

    @classmethod
    def parse(cls, name: str, source: str, rule: Rule | None = None):
        uncommented = JSONC_TOKEN.sub(_remove_comment, source)
        shape = load_json(TRAILING_COMMA.sub(lambda match: "" if match[0] == "," else match[0], uncommented))
        if not isinstance(shape, dict) or not shape:
            raise ValueError("Wzorzec musi zawierać niepusty obiekt JSONC.")

        headers = []
        formatters = {}
        singleton_aliases = {}

        def read_directive(token):
            directive = DIRECTIVE.fullmatch(token[0])
            if not directive:
                return token[0]
            command = directive[1]
            argument = (directive[2] or "").strip()
            if command == "match":
                if not argument:
                    raise ValueError("Dyrektywa @match wymaga wzorca nagłówka.")
                headers.append(re.compile(argument, re.IGNORECASE))
            elif command == "singleton":
                _register_singleton(shape, singleton_aliases, argument)
            else:
                parts = argument.split()
                if len(parts) != 2 or parts[1] not in FORMATTERS:
                    raise ValueError("Dyrektywa @normalize wymaga ścieżki i nazwy formatu.")
                path = tuple(parts[0].split("."))
                field = _field_at(shape, path)
                digits_identifier = parts[1] == "digits" and type(field) is int
                if field is not None and not isinstance(field, str) and not digits_identifier:
                    raise ValueError(f"Formatowanie wymaga pola tekstowego: {parts[0]}")
                if path in formatters:
                    raise ValueError(f"Powtórzona dyrektywa formatowania: {parts[0]}")
                formatters[path] = FORMATTERS[parts[1]]
            return ""

        prompt = JSONC_TOKEN.sub(read_directive, source)
        if not headers:
            title = name.replace("_", " ").replace("-", " ")
            headers.append(re.compile(re.escape(title), re.IGNORECASE))
        return cls(name, prompt, shape, tuple(headers), formatters, rule, singleton_aliases)


def _header_lines(text):
    lines = []
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        spaced_letters = len(words) >= 4 and all(len(word) == 1 and word.isalpha() for word in words)
        lines.append("".join(words) if spaced_letters else " ".join(words))
        if len(lines) == HEADER_LINES:
            break
    return lines


@dataclass(frozen=True)
class TemplateRegistry:
    templates: tuple[DocumentTemplate, ...]

    @classmethod
    def load(cls, directory: Path):
        paths = sorted(directory.glob("*.jsonc"))
        if not paths:
            raise ValueError(f"Brak plików .jsonc w {directory}.")
        return cls(tuple(DocumentTemplate.load(path) for path in paths))

    def classify(self, text: str) -> DocumentTemplate | None:
        lines = _header_lines(text)
        matches = [
            template for template in self.templates
            if any(pattern.fullmatch(line) for line in lines for pattern in template.headers)
        ]
        return matches[0] if len(matches) == 1 else None
