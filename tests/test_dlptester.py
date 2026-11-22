from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from dlptester.cli import main
from dlptester.evaluate import file_verdict, run, score
from dlptester.export import NS, build_xml
from dlptester.extract import extract_text
from dlptester.report import to_html
from dlptester.rules import RulePack, load_pack, scan
from dlptester.validators import card_issuer, luhn, not_repeating

ROOT = Path(__file__).resolve().parent.parent
PACK = load_pack(ROOT / "sits" / "canada.yaml")
CORPUS = ROOT / "samples" / "docs"


def ids(text, min_conf=0):
    return [m.entity_id for m in scan(PACK, text) if m.confidence >= min_conf]


# ---------- validators ----------

@pytest.mark.parametrize("value, ok", [("046 454 286", True), ("046 454 287", False), ("4111111111111111", True),
                                       ("378282246310005", True), ("", False)])
def test_luhn(value, ok):
    assert luhn(value) is ok


def test_card_issuer():
    assert card_issuer("4111 1111 1111 1111") and card_issuer("5555555555554444") and card_issuer("378282246310005")
    assert not card_issuer("9111111111111111") and not card_issuer("411111111111")


def test_not_repeating():
    assert not not_repeating("000 000 000") and not_repeating("046 454 286")


# ---------- matching behaviour ----------

def test_formatted_sin_with_keyword_is_high_confidence():
    [m] = scan(PACK, "Employee SIN: 046-454-286")
    assert m.entity_id == "canada_sin" and m.confidence == 85


def test_unformatted_sin_needs_keyword():
    assert "canada_sin" not in ids("Order 046454286 has shipped")
    assert "canada_sin" in ids("social insurance number 046454286")


def test_invalid_luhn_sin_rejected():
    assert "canada_sin" not in ids("SIN 046 454 287")


def test_keyword_is_whole_word_only():
    assert "canada_sin" not in ids("single sign-on project 046454286", min_conf=75)


def test_keyword_outside_proximity_is_ignored():
    text = "SIN" + " filler" * 100 + " 046454286"
    assert "canada_sin" not in ids(text)


def test_card_needs_luhn_and_issuer():
    assert "payment_card" in ids("visa 4111 1111 1111 1111")
    assert "payment_card" not in ids("visa 4111 1111 1111 1112")


def test_ohip_with_version_code():
    [m] = [m for m in scan(PACK, "Ontario health card 1234-567-897-AB") if m.entity_id == "ontario_health_card"]
    assert m.value.endswith("AB")


def test_masking_hides_all_but_last_three():
    [m] = scan(PACK, "SIN 046 454 286")
    assert m.masked == "••• ••• 286"


# ---------- rule pack validation ----------

def _pack(**over):
    base = dict(name="t", publisher="p", description="d", proximity=50,
                regex={"r": r"\d+"}, keywords={"k": ["x"]}, entities=[])
    base.update(over)
    return base


def test_bad_regex_rejected():
    with pytest.raises(ValueError, match="does not compile"):
        RulePack(**_pack(regex={"r": "("}))


def test_lookbehind_rejected():
    with pytest.raises(ValueError, match="look-behind"):
        RulePack(**_pack(regex={"r": r"(?<=a)\d"}))


def test_unknown_references_rejected(tmp_path):
    data = yaml.safe_load((ROOT / "sits" / "canada.yaml").read_text())
    data["entities"][0]["patterns"][0]["validators"] = ["nope"]
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="unknown validator"):
        load_pack(p)


# ---------- extraction ----------

@pytest.mark.parametrize("name, needle", [("clinic-intake.docx", "OHIP"), ("finance-q3.xlsx", "5555555555554444"),
                                          ("patient-email.eml", "health card"), ("payroll-export.csv", "NS-100002")])
def test_extract_formats(name, needle):
    assert needle in extract_text(CORPUS / name)


# ---------- corpus scoring ----------

def test_sample_corpus_passes():
    results = run(PACK, CORPUS)
    assert all(file_verdict(PACK, r) == "pass" for r in results), [(r.path, file_verdict(PACK, r)) for r in results]
    for s in score(PACK, results).values():
        assert s.precision == 1.0 and s.recall == 1.0


def test_lower_threshold_surfaces_false_positive():
    results = run(PACK, CORPUS)
    verdicts = {r.path: file_verdict(PACK, r, min_conf=65) for r in results}
    assert verdicts["marketing-newsletter.txt"] == "false positive"


def test_missing_expectation_reported(tmp_path):
    (tmp_path / "a.txt").write_text("SIN 046 454 286")
    (tmp_path / "expected.yaml").write_text("a.txt: {}\n")
    [r] = run(PACK, tmp_path)
    assert file_verdict(PACK, r) == "false positive"


# ---------- export + report + CLI ----------

def test_export_is_valid_purview_shape():
    root = ET.fromstring(build_xml(PACK).split("\n", 1)[1])
    q = lambda t: f"{{{NS}}}{t}"  # noqa: E731
    entities = root.findall(f"{q('Rules')}/{q('Entity')}")
    assert len(entities) == len(PACK.entities)
    refs = {m.get("idRef") for m in root.iter(q("IdMatch"))} | {m.get("idRef") for m in root.iter(q("Match"))}
    defined = {e.get("id") for e in root.iter(q("Regex"))} | {e.get("id") for e in root.iter(q("Keyword"))}
    assert refs <= defined
    resources = {r.get("idRef") for r in root.iter(q("Resource"))}
    assert resources == {e.get("id") for e in entities}


def test_export_ids_are_stable():
    assert build_xml(PACK) == build_xml(PACK)


def test_html_masks_values():
    page = to_html(PACK, run(PACK, CORPUS))
    assert "046 454 286" not in page and "286" in page


def test_cli(tmp_path, capsys):
    pack = str(ROOT / "sits" / "canada.yaml")
    assert main(["check", pack]) == 0
    assert main(["test", pack, str(CORPUS), "--html", str(tmp_path / "r.html")]) == 0
    assert main(["test", pack, str(CORPUS), "--min-confidence", "65"]) == 1
    assert main(["export", pack, "-o", str(tmp_path / "x.xml")]) == 0
    raw = (tmp_path / "x.xml").read_bytes()
    assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")  # UTF-16 BOM, as Purview requires
    assert 'encoding="utf-16"' in raw.decode("utf-16")
    assert main(["export", pack, "-o", str(tmp_path / "y.xml"), "--utf8"]) == 0
    assert (tmp_path / "y.xml").read_text(encoding="utf-8").startswith("<?xml")
