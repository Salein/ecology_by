from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=str(cwd))
    return int(p.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parser golden pipeline: generate candidates -> merge -> pytest"
    )
    parser.add_argument("--limit", type=int, default=30, help="Max candidates to generate from DB")
    parser.add_argument("--max-add", type=int, default=20, help="Max candidates to merge into main golden")
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip candidate generation step",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip merge step",
    )
    parser.add_argument(
        "--pytest-target",
        default="tests/test_registry_parser_golden_cases.py",
        help="Pytest target path or expression",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    failed = False

    if not args.skip_generate:
        rc = _run(
            [
                sys.executable,
                "scripts/extract_parser_golden_candidates.py",
                "--limit",
                str(max(1, int(args.limit))),
            ],
            root,
        )
        if rc != 0:
            failed = True

    if not failed and not args.skip_merge:
        rc = _run(
            [
                sys.executable,
                "scripts/merge_parser_golden_candidates.py",
                "--max-add",
                str(max(1, int(args.max_add))),
            ],
            root,
        )
        if rc != 0:
            failed = True

    if not failed:
        rc = _run([sys.executable, "-m", "pytest", "-q", args.pytest_target], root)
        if rc != 0:
            failed = True

    if failed:
        print("parser golden pipeline: FAILED")
        raise SystemExit(1)

    print("parser golden pipeline: OK")


if __name__ == "__main__":
    main()
