from __future__ import annotations

import hashlib
import re


def camelize(text: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", text)
    parts = [part for part in parts if part]
    if not parts:
        return "Field"

    first = parts[0]
    camel = first[0].upper() + first[1:]
    for part in parts[1:]:
        camel += part.capitalize()
    return camel or "Field"


def stable_id(text: str, length: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def slug(text: str, *, suffix: str) -> str:
    base = camelize(text)
    if suffix:
        max_base_len = max(1, 64 - len(suffix))
        base = base[:max_base_len]
        candidate = f"{base}{suffix}"
    else:
        candidate = base[:64]

    if candidate and candidate[0].isdigit():
        candidate = f"F{candidate[:-1]}" if len(candidate) == 64 else f"F{candidate}"
    return candidate or "Field"


def var_name(prefix: str, path: str) -> str:
    slugged = slug(path, suffix=stable_id(path))
    candidate = f"{prefix}{slugged[0].upper()}{slugged[1:]}" if slugged else prefix
    return candidate[:64]


def normalize_ruleset_name(text: str) -> str:
    return slug(text, suffix="") or "StructureMap"
