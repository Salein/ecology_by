from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _case_key(case: dict[str, Any]) -> tuple[str, Any, str]:
    text = str(case.get("text") or "").strip()
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    rid = expected.get("id")
    waste_code = str(expected.get("waste_code") or "")
    return (text, rid, waste_code)


def _normalized_case(case: dict[str, Any], idx: int) -> dict[str, Any]:
    out = dict(case)
    out.setdefault("name", f"merged_candidate_{idx:03d}")
    out.setdefault("source_part", 1)
    out.setdefault("text", "")
    if not isinstance(out.get("expected"), dict):
        out["expected"] = {"count": 1}
    else:
        out["expected"] = dict(out["expected"])
        out["expected"].setdefault("count", 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge parser golden candidates into main golden fixture")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("tests/fixtures/registry_parser_golden_candidates.json"),
        help="Source candidates JSON file",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("tests/fixtures/registry_parser_golden_cases.json"),
        help="Target main golden JSON file",
    )
    parser.add_argument(
        "--max-add",
        type=int,
        default=20,
        help="Maximum new cases to add in one merge",
    )
    args = parser.parse_args()

    source_cases = _load_json(args.source)
    target_cases = _load_json(args.target)
    seen = {_case_key(c) for c in target_cases}

    added = 0
    skipped = 0
    for idx, case in enumerate(source_cases, start=1):
        if added >= max(1, args.max_add):
            break
        key = _case_key(case)
        if key in seen or not key[0]:
            skipped += 1
            continue
        merged = _normalized_case(case, len(target_cases) + 1)
        target_cases.append(merged)
        seen.add(key)
        added += 1

    args.target.write_text(json.dumps(target_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"merged candidates: source={len(source_cases)} target={len(target_cases)} "
        f"added={added} skipped={skipped}"
    )


if __name__ == "__main__":
    main()
