"""Console and HTML reporting. Matched values are always masked."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from . import __version__
from .evaluate import FileResult, file_verdict, score
from .rules import RulePack

_VERDICT_COLORS = {"pass": "#15803d", "false positive": "#b45309", "missed": "#b91c1c", "error": "#6b7280", "n/a": "#6b7280"}


def console(pack: RulePack, results: list[FileResult], min_conf: int | None = None) -> str:
    out = []
    for r in results:
        v = file_verdict(pack, r, min_conf)
        tag = f"[{v.upper()}]" if v != "n/a" else ""
        out.append(f"{r.path} {tag}".rstrip())
        if r.error:
            out.append(f"    ! {r.error}")
        for m in r.matches:
            out.append(f"    {m.confidence:>3}%  {m.entity_id:<26} {m.masked:<22} {'; '.join(m.evidence)}")
        if r.expected is not None and v != "pass":
            out.append(f"    expected: {json.dumps(r.expected)}  found: {dict(r.counts(pack, min_conf))}")
    scores = score(pack, results, min_conf)
    if any(r.expected is not None for r in results):
        out.append("\nEntity scores (at recommended confidence):")
        for ent in pack.entities:
            s = scores[ent.id]
            out.append(f"  {ent.id:<28} precision {s.precision:6.1%}  recall {s.recall:6.1%}  (TP {s.tp} / FP {s.fp} / FN {s.fn})")
    return "\n".join(out)


def _e(v: object) -> str:
    return html.escape(str(v), quote=True)


def to_html(pack: RulePack, results: list[FileResult], min_conf: int | None = None) -> str:
    scores = score(pack, results, min_conf)
    names = {e.id: e.name for e in pack.entities}
    score_rows = "".join(
        f"<tr><td>{_e(names[k])}</td><td>{s.precision:.0%}</td><td>{s.recall:.0%}</td><td>{s.tp}</td><td>{s.fp}</td><td>{s.fn}</td></tr>"
        for k, s in scores.items()
    )
    file_cards = []
    for r in results:
        v = file_verdict(pack, r, min_conf)
        rows = "".join(
            f"<tr><td>{m.confidence}%</td><td>{_e(names.get(m.entity_id, m.entity_id))}</td>"
            f"<td class='mono'>{_e(m.masked)}</td><td>{_e('; '.join(m.evidence))}</td></tr>"
            for m in r.matches
        ) or "<tr><td colspan=4 class='muted'>No matches</td></tr>"
        exp = f"<p class='muted'>Expected: {_e(json.dumps(r.expected))}</p>" if r.expected is not None else ""
        err = f"<p class='err'>{_e(r.error)}</p>" if r.error else ""
        file_cards.append(
            f"<section class='card'><header><h3 class='mono'>{_e(r.path)}</h3>"
            f"<span class='badge' style='background:{_VERDICT_COLORS[v]}'>{_e(v)}</span></header>{err}{exp}"
            f"<div class='tw'><table><thead><tr><th>Conf.</th><th>Type</th><th>Value (masked)</th><th>Evidence</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></section>"
        )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DLP test report: {_e(pack.name)}</title>
<style>
:root{{--bg:#f6f4f0;--card:#fff;--ink:#16181d;--muted:#5b6270;--line:#e4dfd6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14161a;--card:#1c1f25;--ink:#eceae6;--muted:#a3a9b5;--line:#2c3038}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1040px;margin:0 auto;padding:32px 16px 64px}}.mono{{font-family:ui-monospace,Menlo,monospace}}.muted{{color:var(--muted)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}}
header{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}}h3{{margin:0;font-size:15px;word-break:break-all}}
.badge{{color:#fff;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;text-transform:capitalize}}
.tw{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}}th,td{{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600}}.err{{color:#b91c1c}}
</style></head><body><div class="wrap">
<h1>DLP test report</h1><p class="muted">{_e(pack.name)} · {len(results)} files · generated {generated} · values masked</p>
<section class="card"><h2 style="margin:0 0 4px;font-size:18px">Scores at recommended confidence</h2><div class="tw"><table>
<thead><tr><th>Sensitive info type</th><th>Precision</th><th>Recall</th><th>TP</th><th>FP</th><th>FN</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>
{''.join(file_cards)}
<p class="muted">purview-dlp-tester v{__version__} · github.com/CadGoose/purview-dlp-tester</p></div></body></html>"""
