"""Export a rule pack as a Microsoft Purview custom SIT rule package (XML).

Upload with Security & Compliance PowerShell:
    New-DlpSensitiveInformationTypeRulePackage -FileData ([System.IO.File]::ReadAllBytes("rulepack.xml"))

Checksum validators (Luhn, issuer prefix) are evaluated by this tester but are not
emitted into the XML: Purview's custom checksum validator uses a weighted-sum model
that cannot express Luhn. After upload, open each SIT in the Purview portal and enable
"Luhn check" under *Additional checks* (see README).
"""

from __future__ import annotations

import uuid
from xml.etree import ElementTree as ET

from .rules import RulePack

NS = "http://schemas.microsoft.com/office/2011/mce"
_NAMESPACE = uuid.UUID("2b8f0c1d-5a6e-4f7b-9c3d-1e2f3a4b5c6d")


def _guid(*parts: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "/".join(parts)))


def build_xml(pack: RulePack) -> str:
    ET.register_namespace("", NS)
    q = lambda tag: f"{{{NS}}}{tag}"  # noqa: E731

    root = ET.Element(q("RulePackage"))
    rp = ET.SubElement(root, q("RulePack"), id=_guid("pack", pack.name))
    ET.SubElement(rp, q("Version"), major="1", minor="0", build="0", revision="0")
    ET.SubElement(rp, q("Publisher"), id=_guid("publisher", pack.publisher or "unknown"))
    details = ET.SubElement(rp, q("Details"), defaultLangCode="en-us")
    loc = ET.SubElement(details, q("LocalizedDetails"), langcode="en-us")
    ET.SubElement(loc, q("PublisherName")).text = pack.publisher or "Unknown"
    ET.SubElement(loc, q("Name")).text = pack.name
    ET.SubElement(loc, q("Description")).text = pack.description or pack.name

    rules = ET.SubElement(root, q("Rules"))
    used_regex: set[str] = set()
    used_kw: set[str] = set()
    for ent in pack.entities:
        e = ET.SubElement(rules, q("Entity"), id=_guid("entity", ent.id),
                          patternsProximity=str(pack.proximity), recommendedConfidence=str(ent.recommended_confidence))
        for pat in ent.patterns:
            p = ET.SubElement(e, q("Pattern"), confidenceLevel=str(pat.confidence))
            ET.SubElement(p, q("IdMatch"), idRef=f"Regex_{pat.primary}")
            used_regex.add(pat.primary)
            for g in pat.require_all:
                ref = f"Keyword_{g}" if g in pack.keywords else f"Regex_{g}"
                (used_kw if g in pack.keywords else used_regex).add(g)
                ET.SubElement(p, q("Match"), idRef=ref)
            if pat.require_any:
                anyel = ET.SubElement(p, q("Any"), minMatches="1")
                for g in pat.require_any:
                    ref = f"Keyword_{g}" if g in pack.keywords else f"Regex_{g}"
                    (used_kw if g in pack.keywords else used_regex).add(g)
                    ET.SubElement(anyel, q("Match"), idRef=ref)

    for name in sorted(used_regex):
        ET.SubElement(rules, q("Regex"), id=f"Regex_{name}").text = pack.regex[name]
    for name in sorted(used_kw):
        kw = ET.SubElement(rules, q("Keyword"), id=f"Keyword_{name}")
        grp = ET.SubElement(kw, q("Group"), matchStyle="word")
        for term in pack.keywords[name]:
            ET.SubElement(grp, q("Term"), caseSensitive="false").text = term

    strings = ET.SubElement(rules, q("LocalizedStrings"))
    for ent in pack.entities:
        res = ET.SubElement(strings, q("Resource"), idRef=_guid("entity", ent.id))
        ET.SubElement(res, q("Name"), default="true", langcode="en-us").text = ent.name
        ET.SubElement(res, q("Description"), default="true", langcode="en-us").text = ent.description or ent.name

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
