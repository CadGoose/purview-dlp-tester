"""Regenerate the sample corpus in samples/docs.

All identifiers are fictitious:
  * SINs start with 0, a range Service Canada never assigns to people.
  * Card numbers are the industry's published test PANs.
  * Health numbers are obviously sequential (1234567897, 9876543217).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "samples" / "docs"

FILES = {
    "hr-onboarding-letter.txt": """Welcome to North Shield Technology!

To complete payroll setup we have recorded your Social Insurance Number as 046 454 286.
Your employee number is NS-104233. Please bring two pieces of ID on your first day.
""",
    "payroll-export.csv": """Employee,Name,SIN,Province
NS-100001,Avery Tremblay,012345674,ON
NS-100002,Jordan Nguyen,098765431,ON
NS-100003,Sam Patel,046454287,QC
""",
    "invoice-2026-114.txt": """INVOICE 2026-114
Bill to: Contoso Ltd.

Paid by Visa ending 1111 (card number 4111 1111 1111 1111, exp 08/29).
Order number: 4111111111111112
Tracking: 1Z 999 AA1 01 2345 6784
""",
    "marketing-newsletter.txt": """November newsletter

Call us at 416-555-0199 or 1-800-555-0123. Reference code 098 765 431.
Our single sign-on rollout finished this week. Order #123456782 shipped.
""",
}

EML = """From: patient.services@clinic.example
To: frontdesk@clinic.example
Subject: Updated health card
Content-Type: text/plain; charset=utf-8

Hi team, the patient's new Ontario health card number is 1234-567-897-AB.
Please update the chart before Thursday's appointment.
"""

DOCX_PARAS = [
    "Clinic intake form",
    "Patient OHIP: 9876543217",
    "Emergency contact: Riley Chen, 519-555-0144",
    "For tax receipts please provide your SIN: 013 579 131",
]

XLSX_ROWS = [
    ["Q3 corporate card reconciliation", ""],
    ["Card number", "Holder"],
    ["5555555555554444", "Finance - Mastercard"],
    ["378282246310005", "Executive - American Express"],
]


def write_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(p)}</w:t></w:r></w:p>" for p in paragraphs)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)


def write_xlsx(path: Path, rows: list[list[str]]) -> None:
    def col(i: int) -> str:
        return chr(ord("A") + i)
    sheet_rows = "".join(
        f'<row r="{r + 1}">' + "".join(
            f'<c r="{col(c)}{r + 1}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for c, v in enumerate(row) if v
        ) + "</row>"
        for r, row in enumerate(rows)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Q3" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f"<sheetData>{sheet_rows}</sheetData></worksheet>")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in FILES.items():
        (OUT / name).write_text(text, encoding="utf-8")
    (OUT / "patient-email.eml").write_text(EML, encoding="utf-8")
    write_docx(OUT / "clinic-intake.docx", DOCX_PARAS)
    write_xlsx(OUT / "finance-q3.xlsx", XLSX_ROWS)
    print(f"Wrote samples to {OUT}")


if __name__ == "__main__":
    main()
