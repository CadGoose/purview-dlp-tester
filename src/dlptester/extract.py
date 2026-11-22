"""Extract text from the file types DLP usually sees. Office formats use only the stdlib."""

from __future__ import annotations

import email
import re
import zipfile
from email import policy
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_SUFFIXES = {".txt", ".csv", ".tsv", ".md", ".log", ".json", ".xml", ".html", ".htm"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class UnsupportedFile(Exception):
    pass


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(f"{W}p"):
        paras.append("".join(t.text or "" for t in p.iter(f"{W}t")))
    return "\n".join(paras)


def _xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{S}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{S}t")))
        lines = []
        for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            for row in ET.fromstring(z.read(name)).iter(f"{S}row"):
                cells = []
                for c in row.iter(f"{S}c"):
                    v = c.find(f"{S}v")
                    if c.get("t") == "s" and v is not None:
                        cells.append(shared[int(v.text)])
                    elif c.get("t") == "inlineStr":
                        cells.append("".join(t.text or "" for t in c.iter(f"{S}t")))
                    elif v is not None:
                        cells.append(v.text or "")
                lines.append("\t".join(cells))
    return "\n".join(lines)


def _eml(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    parts = [f"Subject: {msg.get('subject', '')}"]
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            parts.append(part.get_content())
    return "\n".join(parts)


def _pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError as exc:
        raise UnsupportedFile("PDF support needs: pip install 'purview-dlp-tester[pdf]'") from exc
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def extract_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return p.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        return _docx(p)
    if suffix == ".xlsx":
        return _xlsx(p)
    if suffix == ".eml":
        return _eml(p)
    if suffix == ".pdf":
        return _pdf(p)
    raise UnsupportedFile(f"unsupported file type: {suffix}")


def iter_files(target: str | Path):
    p = Path(target)
    if p.is_file():
        yield p
        return
    for f in sorted(p.rglob("*")):
        if f.is_file() and not f.name.startswith(".") and f.name != "expected.yaml":
            yield f
