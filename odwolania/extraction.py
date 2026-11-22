"""Extract canonical JSON from a pseudonymized document using a language model."""

import argparse
import json
import logging
import math
import re
import sys
from pathlib import Path

from .mistral import MistralClient
from .rules import empty_result
from .templates import POLISH_KEY_LETTERS, DocumentTemplate, load_json, normalize_spaces

LOG = logging.getLogger(__name__)

MARKER = re.compile(r"\[([A-Z_]+)_\d+\]", re.IGNORECASE)
MARKER_TYPE = re.compile(r"\[([A-Z_]+)\]")
JSON_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", re.IGNORECASE | re.DOTALL)

class DocumentExtractor:
    def __init__(self, client):
        self.client = client

    def extract(self, text_path, template_path):
        document = text_path.read_text(encoding="utf-8")
        template = DocumentTemplate.load(template_path)
        mapping = load_json(text_path.with_suffix(".mapa.json").read_text(encoding="utf-8"))
        return self.extract_text(document, template, mapping)

    def extract_text(self, document, template: DocumentTemplate, mapping, *, local_fields=()):
        if not isinstance(mapping, dict) or not all(isinstance(value, str) for value in mapping.values()):
            raise ValueError("Mapa musi zawierać obiekt z wartościami tekstowymi.")
        allowed_markers = {match[0] for match in MARKER.finditer(document)}
        if not allowed_markers <= mapping.keys():
            raise ValueError("Tekst musi zawierać znaczniki zgodne z mapą dokumentu.")
        prompt = template.prompt
        if local_fields:
            paths = json.dumps(sorted(local_fields), ensure_ascii=False)
            prompt += ("\n\nPola pod wskazanymi ścieżkami ustalił program lokalnie. "
                       "Zachowaj ich klucze i zwróć w nich null. Wyodrębnij pozostałe pola.\n" + paths)
        try:
            response = self.client.complete(prompt, document).strip()
            fence = JSON_FENCE.fullmatch(response)
            answer = load_json(fence[1] if fence else response)
        except ValueError:
            LOG.warning("Nie można odczytać odpowiedzi JSON. Wykorzystuję pola z reguł lokalnych.")
            return empty_result(template.shape)

        # Some responses add the document type as a single extra level above the expected fields.
        if isinstance(answer, dict) and answer.keys() == {template.name} and template.name not in template.shape:
            wrapped = answer[template.name]
            if isinstance(wrapped, dict):
                answer = wrapped
        try:
            return validate_result(template.shape, answer, template.formatters,
                                   tags=allowed_markers, local_fields=local_fields)
        except ValueError:
            result, count = recover_fields(template.shape, answer, template.formatters, tags=allowed_markers,
                                           local_fields=local_fields, singleton_aliases=template.singleton_aliases)
            LOG.warning("Odpowiedź niezgodna ze wzorcem. Odzyskano lokalnie %d wartości modelu.", count)
            return result


def _recover_object_keys(shape, value, singleton_aliases):
    """Match Polish spelling variants only when both objects have one unambiguous key."""
    targets = {}
    for key in shape:
        spelling = key.translate(POLISH_KEY_LETTERS)
        targets[spelling] = None if spelling in targets else key

    recovered = value.copy()
    for key, field in value.items():
        target = targets.get(key.translate(POLISH_KEY_LETTERS))
        if target is not None and target not in value:
            # A second spelling in the response makes this alias ambiguous.
            recovered[target] = None if target in recovered else field
    for target, alias in singleton_aliases.items():
        if target not in recovered and isinstance(value.get(alias), dict):
            recovered[target] = [value[alias]]
    return recovered


def recover_fields(shape, value, formatters, path=(), *, tags, local_fields, singleton_aliases=None):
    """Keep validated fields from one response and count recovered non-null values."""
    if value is None or path in local_fields:
        return empty_result(shape), 0
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return empty_result(shape), 0
        selector = tuple("*" if type(part) is int else part for part in path)
        aliases = singleton_aliases.get(selector, {}) if singleton_aliases else {}
        value = _recover_object_keys(shape, value, aliases)
        result = {}
        count = 0
        for key, field in shape.items():
            result[key], found = recover_fields(field, value.get(key), formatters, (*path, key), tags=tags,
                                                local_fields=local_fields, singleton_aliases=singleton_aliases)
            count += found
        return result, count
    if isinstance(shape, list):
        items, count = [], 0
        if isinstance(value, list) and shape:
            for index, row in enumerate(value):
                item, found = recover_fields(shape[0], row, formatters, (*path, index), tags=tags,
                                             local_fields=local_fields, singleton_aliases=singleton_aliases)
                if found:
                    items.append(item)
                    count += found
        return items, count
    try:
        valid = validate_result(shape, value, formatters, path, tags=tags, local_fields=local_fields)
    except ValueError:
        return None, 0
    return valid, 1


def validate_result(shape, value, formatters, path=(), *, tags=None, local_fields=()):
    if path in local_fields:
        return None
    location = "$" + "".join(f"[{part}]" if type(part) is int else f".{part}" for part in path)
    if isinstance(shape, dict):
        if not isinstance(value, dict) or value.keys() != shape.keys():
            raise ValueError(f"Odpowiedź zmieniła klucze obiektu {location}.")
        return {
            key: validate_result(field, value[key], formatters, (*path, key), tags=tags, local_fields=local_fields)
            for key, field in shape.items()
        }
    if isinstance(shape, list):
        if not isinstance(value, list):
            raise ValueError(f"Pole {location} musi być listą.")
        if not shape and value:
            raise ValueError(f"Wzorzec nie określa elementów listy {location}.")
        return [
            validate_result(shape[0], item, formatters, (*path, index), tags=tags, local_fields=local_fields)
            for index, item in enumerate(value)
        ]
    if value is None:
        return None
    selector = tuple("*" if type(part) is int else part for part in path)
    if selector in formatters:
        compatible = isinstance(value, str) or (type(shape) is int and type(value) is int)
    elif shape is None:
        compatible = type(value) in {str, int, float, bool}
    elif type(shape) is float:
        compatible = type(value) in {int, float}
    else:
        compatible = type(value) is type(shape)
    if not compatible or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"Odpowiedź zmieniła typ pola {location}.")
    if tags is not None and isinstance(value, str):
        if any(match[0] not in tags for match in MARKER.finditer(value)):
            raise ValueError(f"Pole {location} zawiera znacznik spoza dokumentu.")
        marker_type = MARKER_TYPE.fullmatch(shape) if isinstance(shape, str) else None
        if marker_type:
            tokens = value.split()
            prefix = f"[{marker_type[1]}_"
            if not tokens or any(tag not in tags or not tag.startswith(prefix) for tag in tokens):
                raise ValueError(f"Pole {location} wymaga znaczników typu {marker_type[1]}.")
    return value


def restore_markers(value, mapping, formatters=None, path=()):
    return format_result(value, formatters, path, mapping=mapping)


def format_result(value, formatters, path=(), *, mapping=None):
    if isinstance(value, dict):
        return {
            key: format_result(field, formatters, (*path, key), mapping=mapping)
            for key, field in value.items()
        }
    if isinstance(value, list):
        return [format_result(item, formatters, (*path, "*"), mapping=mapping) for item in value]
    formatter = formatters.get(path) if formatters else None
    if isinstance(value, str):
        restored = MARKER.sub(lambda marker: mapping[marker[0]], value) if mapping is not None else value
        return normalize_spaces(formatter(restored) if formatter else restored)
    if formatter and type(value) is int:
        return formatter(str(value))
    return value


def main(argv):
    parser = argparse.ArgumentParser(prog="odwolania extract", description="Zwróć JSON ze znacznikami z dokumentu")
    parser.add_argument("--model", help="Identyfikator modelu Mistral. Nadpisuje MISTRAL_MODEL.")
    parser.add_argument("text", type=Path, nargs="?", default=Path("output/przyklad_04/odwolanie.txt"))
    parser.add_argument("template", type=Path, nargs="?", default=Path("oczekiwane-json/odwolanie.jsonc"))
    args = parser.parse_args(argv)
    try:
        client = MistralClient.from_environment(args.model)
    except ValueError as error:
        parser.error(str(error))
    try:
        result = DocumentExtractor(client).extract(args.text, args.template)
        output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Ekstrakcja nie powiodła się. {error}", file=sys.stderr)
        return 1
    print(output)
    return 0
