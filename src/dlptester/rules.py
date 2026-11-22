"""Load a SIT rule pack (YAML) and evaluate it against text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .validators import VALIDATORS


@dataclass
class Pattern:
    confidence: int
    primary: str
    validators: list[str] = field(default_factory=list)
    require_any: list[str] = field(default_factory=list)  # at least one keyword group must match nearby
    require_all: list[str] = field(default_factory=list)  # every listed group must match nearby


@dataclass
class Entity:
    id: str
    name: str
    description: str
    recommended_confidence: int
    patterns: list[Pattern]


@dataclass
class RulePack:
    name: str
    publisher: str
    description: str
    proximity: int
    regex: dict[str, str]
    keywords: dict[str, list[str]]
    entities: list[Entity]
    _compiled: dict[str, re.Pattern] = field(default_factory=dict, repr=False)
    _kw_compiled: dict[str, re.Pattern] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        errors = validate_pack(self)
        if errors:
            raise ValueError("invalid rule pack:\n  " + "\n  ".join(errors))
        self._compiled = {k: re.compile(v) for k, v in self.regex.items()}
        # Keywords match on word boundaries, case-insensitive (Purview "word" match style).
        self._kw_compiled = {
            k: re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")(?!\w)",
                          re.IGNORECASE)
            for k, terms in self.keywords.items()
        }

    def entity(self, entity_id: str) -> Entity:
        for e in self.entities:
            if e.id == entity_id:
                return e
        raise KeyError(entity_id)


def validate_pack(pack: RulePack) -> list[str]:
    errors: list[str] = []
    for name, rx in pack.regex.items():
        try:
            re.compile(rx)
        except re.error as exc:
            errors.append(f"regex '{name}' does not compile: {exc}")
        if "(?<=" in rx or "(?<!" in rx:
            errors.append(f"regex '{name}' uses look-behind, which Purview does not support")
    ids = set()
    for e in pack.entities:
        if e.id in ids:
            errors.append(f"duplicate entity id '{e.id}'")
        ids.add(e.id)
        if not e.patterns:
            errors.append(f"entity '{e.id}' has no patterns")
        for p in e.patterns:
            if p.primary not in pack.regex:
                errors.append(f"entity '{e.id}': primary '{p.primary}' is not a defined regex")
            for v in p.validators:
                if v not in VALIDATORS:
                    errors.append(f"entity '{e.id}': unknown validator '{v}' (known: {', '.join(VALIDATORS)})")
            for g in p.require_any + p.require_all:
                if g not in pack.keywords and g not in pack.regex:
                    errors.append(f"entity '{e.id}': supporting element '{g}' is not defined")
            if not 1 <= p.confidence <= 100:
                errors.append(f"entity '{e.id}': confidence must be 1-100")
    return errors


def load_pack(path: str | Path) -> RulePack:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rp = data.get("rule_pack", {})
    els = data.get("elements", {})
    entities = [
        Entity(
            id=e["id"], name=e["name"], description=e.get("description", ""),
            recommended_confidence=int(e.get("recommended_confidence", 85)),
            patterns=sorted((Pattern(**p) for p in e.get("patterns", [])), key=lambda p: -p.confidence),
        )
        for e in data.get("entities", [])
    ]
    return RulePack(
        name=rp.get("name", "Custom SITs"), publisher=rp.get("publisher", ""),
        description=rp.get("description", ""), proximity=int(rp.get("proximity", 300)),
        regex=els.get("regex", {}), keywords=els.get("keywords", {}), entities=entities,
    )


@dataclass
class Match:
    entity_id: str
    value: str
    start: int
    end: int
    confidence: int
    evidence: list[str]

    @property
    def masked(self) -> str:
        visible = 3
        chars = [c if not c.isalnum() else "•" for c in self.value]
        alnum_idx = [i for i, c in enumerate(self.value) if c.isalnum()]
        for i in alnum_idx[-visible:]:
            chars[i] = self.value[i]
        return "".join(chars)


def _supporting_hit(pack: RulePack, group: str, window: str) -> str | None:
    rx = pack._kw_compiled.get(group) or pack._compiled.get(group)
    if rx is None:
        return None
    m = rx.search(window)
    return m.group(0) if m else None


def scan(pack: RulePack, text: str) -> list[Match]:
    """Return the best-confidence match per (entity, span)."""
    results: dict[tuple[str, int, int], Match] = {}
    for ent in pack.entities:
        for pat in ent.patterns:  # highest confidence first
            for m in pack._compiled[pat.primary].finditer(text):
                key = (ent.id, m.start(), m.end())
                if key in results:
                    continue
                value = m.group(0)
                if not all(VALIDATORS[v](value) for v in pat.validators):
                    continue
                lo, hi = max(0, m.start() - pack.proximity), min(len(text), m.end() + pack.proximity)
                window = text[lo:m.start()] + " " + text[m.end():hi]
                evidence: list[str] = []
                ok = True
                if pat.require_all:
                    for g in pat.require_all:
                        hit = _supporting_hit(pack, g, window)
                        if not hit:
                            ok = False
                            break
                        evidence.append(f"{g}: '{hit}'")
                if ok and pat.require_any:
                    hits = [(g, _supporting_hit(pack, g, window)) for g in pat.require_any]
                    hits = [(g, h) for g, h in hits if h]
                    ok = bool(hits)
                    evidence += [f"{g}: '{h}'" for g, h in hits]
                if not ok:
                    continue
                if pat.validators:
                    evidence.insert(0, "passed " + ", ".join(pat.validators))
                results[key] = Match(ent.id, value, m.start(), m.end(), pat.confidence, evidence)
    # Drop matches fully contained in a higher-confidence match of the same entity.
    ordered = sorted(results.values(), key=lambda x: (x.entity_id, x.start, -(x.end - x.start)))
    kept: list[Match] = []
    for mt in ordered:
        if any(k.entity_id == mt.entity_id and k.start <= mt.start and mt.end <= k.end for k in kept):
            continue
        kept.append(mt)
    return sorted(kept, key=lambda x: x.start)
