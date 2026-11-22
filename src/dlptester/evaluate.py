"""Run a rule pack over a corpus and score it against expected results."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .extract import UnsupportedFile, extract_text, iter_files
from .rules import Match, RulePack, scan


@dataclass
class FileResult:
    path: str
    matches: list[Match] = field(default_factory=list)
    error: str = ""
    expected: dict[str, int] | None = None  # entity -> expected count at/above its threshold

    def counts(self, pack: RulePack, min_conf: int | None = None) -> Counter:
        c: Counter = Counter()
        for m in self.matches:
            threshold = min_conf if min_conf is not None else pack.entity(m.entity_id).recommended_confidence
            if m.confidence >= threshold:
                c[m.entity_id] += 1
        return c


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


def load_expected(path: Path) -> dict[str, dict[str, int]]:
    """expected.yaml maps relative file path -> {entity_id: count}. Missing entities mean 0."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): {ek: int(ev) for ek, ev in (v or {}).items()} for k, v in data.items()}


def run(pack: RulePack, target: str | Path, expected_file: str | Path | None = None) -> list[FileResult]:
    target = Path(target)
    base = target if target.is_dir() else target.parent
    exp_path = Path(expected_file) if expected_file else base / "expected.yaml"
    expected = load_expected(exp_path)
    results = []
    for f in iter_files(target):
        rel = f.relative_to(base).as_posix()
        r = FileResult(rel, expected=expected.get(rel) if expected else None)
        if expected and rel not in expected:
            r.expected = {}
        try:
            r.matches = scan(pack, extract_text(f))
        except UnsupportedFile as exc:
            r.error = str(exc)
        except Exception as exc:  # corrupt file etc. - report, keep going
            r.error = f"{type(exc).__name__}: {exc}"
        results.append(r)
    return results


def score(pack: RulePack, results: list[FileResult], min_conf: int | None = None) -> dict[str, Score]:
    """Per-entity TP/FP/FN, counted per file (min of expected vs found = TP)."""
    scores = {e.id: Score() for e in pack.entities}
    for r in results:
        if r.expected is None or r.error:
            continue
        found = r.counts(pack, min_conf)
        for ent in pack.entities:
            exp, got = r.expected.get(ent.id, 0), found.get(ent.id, 0)
            s = scores[ent.id]
            s.tp += min(exp, got)
            s.fp += max(0, got - exp)
            s.fn += max(0, exp - got)
    return scores


def file_verdict(pack: RulePack, r: FileResult, min_conf: int | None = None) -> str:
    if r.error:
        return "error"
    if r.expected is None:
        return "n/a"
    found = r.counts(pack, min_conf)
    for ent in pack.entities:
        exp, got = r.expected.get(ent.id, 0), found.get(ent.id, 0)
        if got > exp:
            return "false positive"
        if got < exp:
            return "missed"
    return "pass"
