import json
from pathlib import Path

import pytest

from app.services.registry_record_parser import parse_registry_plain_text


def _load_cases() -> list[dict]:
    p = Path(__file__).parent / "fixtures" / "registry_parser_golden_cases.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_registry_parser_golden_cases(case: dict) -> None:
    rows = parse_registry_plain_text(case["text"], int(case.get("source_part") or 1))
    expected = case["expected"]
    assert len(rows) == int(expected["count"])
    if not rows:
        return

    row = rows[0]
    if "id" in expected:
        assert row["id"] == int(expected["id"])
    if "waste_code" in expected:
        assert row["waste_code"] == expected["waste_code"]

    for token in expected.get("owner_contains", []):
        assert token.casefold() in str(row.get("owner") or "").casefold()
    for token in expected.get("object_contains", []):
        assert token.casefold() in str(row.get("object_name") or "").casefold()
    for token in expected.get("address_contains", []):
        assert token.casefold() in str(row.get("address") or "").casefold()
    for token in expected.get("phones_contains", []):
        assert token.casefold() in str(row.get("phones") or "").casefold()
