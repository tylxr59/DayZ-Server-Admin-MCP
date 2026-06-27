from __future__ import annotations

import ast
import re
from typing import Any

_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*;\s*$")


def strip_line_comment(line: str) -> str:
    in_quote = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if not in_quote and line[index : index + 2] == "//":
            return line[:index]
    return line


def parse_value(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""

    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False

    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_value(part) for part in _split_array(inner)]

    if value.startswith('"') and value.endswith('"'):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def parse_server_config(text: str) -> dict[str, Any]:
    """Parse simple DayZ cfg assignments.

    DayZ config files use an Arma-style syntax with nested classes. This parser
    intentionally extracts assignment lines and ignores class structure.
    """

    parsed: dict[str, Any] = {}

    for line in text.splitlines():
        cleaned = strip_line_comment(line).strip()
        if not cleaned or cleaned.startswith(("class ", "{", "}")):
            continue

        match = _ASSIGNMENT_RE.match(cleaned)
        if not match:
            continue

        key, raw_value = match.groups()
        parsed[key] = parse_value(raw_value)

    return parsed


def _split_array(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == '"':
            current.append(char)
            in_quote = not in_quote
            continue
        if char == "," and not in_quote:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    parts.append("".join(current).strip())
    return [part for part in parts if part]
