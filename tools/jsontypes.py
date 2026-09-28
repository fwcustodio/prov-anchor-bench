"""Typed access to JSON documents from external services (Horizon, Rekor).

External responses are parsed into ``JsonValue`` and narrowed with the
helpers below, so every field access is checked instead of assumed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

JsonValue = Union[None, bool, int, float, str, list["JsonValue"], dict[str, "JsonValue"]]
JsonObject = dict[str, JsonValue]


class JsonShapeError(ValueError):
    """Raised when a JSON document does not have the expected shape."""


def parse_json(text: str) -> JsonValue:
    parsed: JsonValue = json.loads(text)
    return parsed


def read_json(path: Path) -> JsonValue:
    return parse_json(path.read_text(encoding="utf8"))


def write_json(path: Path, value: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf8"
    )


def as_object(value: JsonValue, context: str) -> JsonObject:
    if not isinstance(value, dict):
        raise JsonShapeError(f"{context}: expected a JSON object")
    return value


def as_list(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise JsonShapeError(f"{context}: expected a JSON array")
    return value


def get_str(obj: JsonObject, key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise JsonShapeError(f"{context}: field '{key}' is not a string")
    return value


def get_int(obj: JsonObject, key: str, context: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise JsonShapeError(f"{context}: field '{key}' is not an integer")
    return value


def get_bool(obj: JsonObject, key: str, context: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise JsonShapeError(f"{context}: field '{key}' is not a boolean")
    return value


def get_object(obj: JsonObject, key: str, context: str) -> JsonObject:
    return as_object(obj.get(key), f"{context}.{key}")


def get_list(obj: JsonObject, key: str, context: str) -> list[JsonValue]:
    return as_list(obj.get(key), f"{context}.{key}")
