"""The FACTS the assistant may use. Every value is formatted by the engine, never by the model."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.number_guard import allowed_numbers


@dataclass(frozen=True)
class Fact:
    id: str
    key: str
    label: str
    value: str


class FactSet:
    def __init__(self) -> None:
        self._by_key: dict[str, Fact] = {}
        self._by_id: dict[str, Fact] = {}

    def add(self, key: str, label: str, value: str) -> Fact:
        if key in self._by_key:
            return self._by_key[key]
        fact = Fact(f"fact_{len(self._by_key) + 1}", key, label, value)
        self._by_key[key] = fact
        self._by_id[fact.id] = fact
        return fact

    def selected(self, prefixes: tuple[str, ...]) -> FactSet:
        """Read-only subset preserving engine fact IDs (no renumbering)."""
        result = FactSet()
        for fact in self.all():
            if fact.key.startswith(prefixes):
                result._by_key[fact.key] = fact
                result._by_id[fact.id] = fact
        return result

    def get(self, key: str) -> Fact | None:
        return self._by_key.get(key)

    def value(self, key: str, default: str = "") -> str:
        fact = self._by_key.get(key)
        return fact.value if fact else default

    def has(self, key: str) -> bool:
        return key in self._by_key

    def by_id(self, fact_id: str) -> Fact | None:
        return self._by_id.get(fact_id)

    def ids(self) -> set[str]:
        return set(self._by_id)

    def all(self) -> list[Fact]:
        return list(self._by_key.values())

    def keys_with_prefix(self, prefix: str) -> list[str]:
        return [k for k in self._by_key if k.startswith(prefix)]

    def numbers(self) -> set:
        return allowed_numbers(f.value for f in self._by_key.values())

    def prompt_lines(self) -> list[str]:
        return [f"{f.id} | {f.label} | {f.value}" for f in self._by_key.values()]
