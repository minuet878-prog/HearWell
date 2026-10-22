"""Extract the hearing (b230) assessment hospitals from the MOHW roster XLSX (#222).

Development-only tool; uses the standard library, so nothing is added to any requirements file.

1. Download the latest XLSX of 「各縣市身心障礙類別、向度之鑑定醫院名冊」 from
   https://dep.mohw.gov.tw/DONAHC/cp-1037-5217-104.html into an empty folder of its own.
2. From the repository root run:
       python -I scripts/extract_assessment_hospitals.py <path to 各縣市...名冊1150717.xlsx>
3. It rewrites screening/data/assessment_hospitals.json. Review the diff before committing.

The roster has one visible sheet per county (the hidden 「家數」 sheet is skipped): row 1 holds the
hospital names, column C the assessment codes, and a "v" marks what a hospital can assess.
The version is the seven-digit date in the file name. The roster has no address or phone
columns, so only the names are kept (spec #218).
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OUTPUT = Path(__file__).resolve().parent.parent / "screening" / "data" / "assessment_hospitals.json"


def shared_strings(book):
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(MAIN + "t")) for si in root.iter(MAIN + "si")]


def visible_sheets(book):
    """(sheet name, part path) in workbook order, hidden sheets left out."""
    targets = {
        rel.get("Id"): rel.get("Target")
        for rel in ET.fromstring(book.read("xl/_rels/workbook.xml.rels")).iter(
            PACKAGE_REL + "Relationship"
        )
    }
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    for sheet in workbook.iter(MAIN + "sheet"):
        if sheet.get("state") != "hidden":
            yield sheet.get("name"), "xl/" + targets[sheet.get(REL + "id")].removeprefix("/xl/")


def rows_of(book, part, strings):
    """{row number: {column letters: text}} for the non-empty cells, read as a stream."""
    rows = {}
    with book.open(part) as stream:
        for _, element in ET.iterparse(stream):
            if element.tag == MAIN + "c":
                value = element.find(MAIN + "v")
                text = "" if value is None else value.text or ""
                if element.get("t") == "s":
                    text = strings[int(text)]
                if text.strip():
                    column, row = re.fullmatch(r"([A-Z]+)(\d+)", element.get("r")).groups()
                    rows.setdefault(int(row), {})[column] = text.strip()
                element.clear()
            elif element.tag == MAIN + "row":
                element.clear()
    return rows


def hearing_hospitals(rows):
    names = rows[1]
    hearing = next(cells for cells in rows.values() if cells.get("C", "").startswith("b230"))
    return [
        names[column]
        for column in sorted(names, key=lambda c: (len(c), c))
        if column not in ("A", "B", "C")
        if hearing.get(column, "").lower() == "v"
    ]


def main(path):
    version = re.search(r"\d{7}", Path(path).name).group()
    with zipfile.ZipFile(path) as book:
        strings = shared_strings(book)
        counties, hospitals = [], []
        for county, part in visible_sheets(book):
            counties.append(county)
            for name in hearing_hospitals(rows_of(book, part, strings)):
                hospitals.append({"county": county, "name": name})
    snapshot = {"version": version, "counties": counties, "hospitals": hospitals}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{version}: {len(hospitals)} hospitals in {len(counties)} counties -> {OUTPUT}")


if __name__ == "__main__":
    main(sys.argv[1])
