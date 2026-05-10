from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _db_url() -> str:
    raw = (os.getenv("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL is required")
    return raw.replace("postgresql+psycopg://", "postgresql://")


def _is_empty(v: Any) -> bool:
    return not str(v or "").strip()


def _contains_noise(v: Any) -> bool:
    s = str(v or "").casefold()
    if not s:
        return False
    return any(
        token in s
        for token in (
            "страница ",
            "из 199",
            "в соответствии",
            "об охране окружающей среды",
            "тел.",
            "факс",
        )
    )


def _looks_bad(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _is_empty(row.get("owner")):
        reasons.append("owner_empty")
    if _is_empty(row.get("address")):
        reasons.append("address_empty")
    if _is_empty(row.get("phones")):
        reasons.append("phones_empty")
    if str(row.get("object_name") or "").strip() in {"", "—", "-"}:
        reasons.append("object_placeholder")
    if _contains_noise(row.get("owner")):
        reasons.append("owner_noise")
    if _contains_noise(row.get("object_name")):
        reasons.append("object_noise")
    if _contains_noise(row.get("address")):
        reasons.append("address_noise")
    return reasons


def _as_case_name(idx: int, reasons: list[str], rid: Any) -> str:
    rs = "_".join(reasons[:3]) or "suspicious"
    return f"candidate_{idx:03d}_{rs}_id_{rid}"


def _build_case(idx: int, row: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    rid = int(row.get("record_id") or row.get("id") or 0)
    source_part = int(row.get("source_part") or 1)
    waste_code = str(row.get("waste_code") or "1111111")
    waste_type_name = str(row.get("waste_type_name") or "Вид отхода")
    object_name = str(row.get("object_name") or "").strip()
    owner = str(row.get("owner") or "").strip()
    address = str(row.get("address") or "").strip()
    phones = str(row.get("phones") or "").strip()

    # Synthetic text template for parser regression reproduction.
    lines = [
        f"{waste_code} {waste_type_name}".strip(),
        f"Объект {rid} {object_name}".strip(),
    ]
    if address:
        lines.append(address)
    lines.append("Собственник" if not owner else f"Собственник {owner}")
    if owner and _is_empty(address):
        # If address is missing, include owner block only.
        pass
    elif address:
        lines.append(address)
    if phones:
        lines.append(phones)
    text = "\n".join(lines) + "\n"

    expected: dict[str, Any] = {
        "count": 1,
        "id": rid,
        "waste_code": waste_code,
    }
    if owner:
        expected["owner_contains"] = [x for x in owner.split()[:2] if len(x) > 2]
    if object_name and object_name not in {"—", "-"}:
        expected["object_contains"] = [x for x in object_name.split()[:3] if len(x) > 2]
    if address:
        expected["address_contains"] = [x.strip(",") for x in address.split()[:3] if len(x.strip(",")) > 2]
    if phones:
        expected["phones_contains"] = [phones[:4]]

    return {
        "name": _as_case_name(idx, reasons, rid),
        "source_part": source_part,
        "text": text,
        "expected": expected,
        "meta": {"reasons": reasons},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate parser golden-case candidates from registry cache")
    parser.add_argument("--limit", type=int, default=30, help="Maximum candidate rows to export")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/registry_parser_golden_candidates.json"),
        help="Output JSON path (relative to server/)",
    )
    args = parser.parse_args()

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    q = """
    select
      record_id,
      source_part,
      owner,
      object_name,
      waste_code,
      waste_type_name,
      address,
      phones,
      payload
    from registry_records
    order by pk asc
    """
    picked: list[dict[str, Any]] = []
    with psycopg.connect(_db_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            for row in cur.fetchall():
                reasons = _looks_bad(row)
                if not reasons:
                    continue
                picked.append(_build_case(len(picked) + 1, row, reasons))
                if len(picked) >= max(1, args.limit):
                    break

    out_path.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(picked)} candidates to {out_path}")


if __name__ == "__main__":
    main()
