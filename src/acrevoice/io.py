import csv
import io
import json

# Columns every import row carries regardless of scheme; anything else in the
# row is a scheme field (see schemes.py) and travels through untouched so an
# empty cell still shows up as a missing field for the workflow to call about.
CASE_COLUMNS = ("holding_id", "holding_name", "application_year", "scheme_code")


def record_from_csv(file) -> list[dict]:
    """Parse a FALK-style import CSV into one case dict per row.

    Accepts either an open file object (as FastAPI's ``UploadFile.file`` gives
    us) or raw CSV text. Each row becomes ``{"scheme_code", "holding_name",
    "application_year", "record"}``; ``record`` keeps every column, including
    ``holding_id`` and the scheme-specific fields, so the original row survives
    unedited in the case's ``original_record``.
    """
    text = file.read() if hasattr(file, "read") else file
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), strict=True)
    if not reader.fieldnames or not set(CASE_COLUMNS).issubset(reader.fieldnames):
        raise ValueError("Required columns: " + ", ".join(CASE_COLUMNS))
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("Duplicate CSV column names")
    rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no records")
    cases = []
    for row in rows:
        if None in row:
            raise ValueError("CSV row has more values than its header")
        record = {key: (value or "").strip() for key, value in row.items() if key}
        cases.append({
            "scheme_code": record.get("scheme_code", ""),
            "holding_name": record.get("holding_name", ""),
            "application_year": record.get("application_year", ""),
            "record": record,
        })
    return cases


def correction_csv(package: dict) -> str:
    """Serialize only approved changes for adviser transfer."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["field", "original", "proposed", "confirmed", "question", "captured_at"])
    writer.writeheader()
    for change in package["changes"]:
        writer.writerow({key: ("'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
                         for key, value in change.items()})
    return output.getvalue()


def correction_json(package: dict) -> str:
    return json.dumps(package, indent=2, ensure_ascii=False)
