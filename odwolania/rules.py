"""Discover local rules and identify fields they can fill before model extraction."""

from collections.abc import Callable
from inspect import signature
from pathlib import Path
from runpy import run_path


Rule = Callable[[str, dict], None]


def load_rule(path: Path) -> Rule | None:
    if not path.exists():
        return None
    try:
        rule_class = run_path(str(path)).get(path.stem)
        if not isinstance(rule_class, type):
            raise ValueError(f"Brak klasy {path.stem}.")
        apply = rule_class().zastosuj
        signature(apply).bind("", {})
        return apply
    except Exception as error:
        raise ValueError(f"{path.name}: błędna klasa reguł. {error}") from error


def empty_result(shape):
    if isinstance(shape, dict):
        return {key: empty_result(field) for key, field in shape.items()}
    if isinstance(shape, list):
        return []
    return None


def field_values(result, path=()):
    for key, value in result.items():
        field = (*path, key)
        if isinstance(value, dict):
            yield from field_values(value, field)
        else:
            yield field, value


def set_fields(result, fields):
    for path, value in fields.items():
        target = result
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
