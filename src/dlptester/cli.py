"""Command line interface: `dlp-tester test | scan | export | check`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .evaluate import file_verdict, run
from .export import build_xml
from .extract import extract_text
from .report import console, to_html
from .rules import load_pack, scan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dlp-tester", description="Test custom Purview sensitive information types locally.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("test", help="run a rule pack over a corpus and score against expected.yaml")
    t.add_argument("rulepack")
    t.add_argument("corpus", help="folder (or single file) of sample documents")
    t.add_argument("--expected", help="expected results YAML (default: <corpus>/expected.yaml)")
    t.add_argument("--min-confidence", type=int, help="override each entity's recommended confidence")
    t.add_argument("--html", help="write an HTML report")

    s = sub.add_parser("scan", help="scan text or a file and print matches (no scoring)")
    s.add_argument("rulepack")
    s.add_argument("input", help="file path, or '-' to read stdin")

    e = sub.add_parser("export", help="export Purview rule package XML")
    e.add_argument("rulepack")
    e.add_argument("-o", "--output", default="rulepack.xml")
    e.add_argument("--utf8", action="store_true", help="write UTF-8 for reading/diffing (Purview upload needs the default UTF-16)")

    c = sub.add_parser("check", help="validate a rule pack (regex compile, references, Purview compatibility)")
    c.add_argument("rulepack")

    args = p.parse_args(argv)
    try:
        pack = load_pack(args.rulepack)
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.cmd == "check":
        print(f"OK: {len(pack.entities)} entities, {len(pack.regex)} regexes, {len(pack.keywords)} keyword lists.")
        return 0

    if args.cmd == "export":
        xml = build_xml(pack)
        if args.utf8:
            Path(args.output).write_text(xml, encoding="utf-8")
        else:
            Path(args.output).write_text(xml.replace('encoding="utf-8"', 'encoding="utf-16"', 1), encoding="utf-16")
        print(f"Wrote {args.output}. Upload with New-DlpSensitiveInformationTypeRulePackage, then enable Luhn checks in the portal (see README).")
        return 0

    if args.cmd == "scan":
        text = sys.stdin.read() if args.input == "-" else extract_text(args.input)
        for m in scan(pack, text):
            print(f"{m.confidence:>3}%  {m.entity_id:<26} {m.masked:<22} {'; '.join(m.evidence)}")
        return 0

    results = run(pack, args.corpus, args.expected)
    print(console(pack, results, args.min_confidence))
    if args.html:
        Path(args.html).write_text(to_html(pack, results, args.min_confidence), encoding="utf-8")
        print(f"\nHTML report: {args.html}")
    failed = [r for r in results if file_verdict(pack, r, args.min_confidence) in ("false positive", "missed", "error")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
