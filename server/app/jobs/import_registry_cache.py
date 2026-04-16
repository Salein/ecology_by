from __future__ import annotations

import json
from pathlib import Path

from app.services.user_registry_cache import save_geocode_cache, save_user_registry_cache

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REGISTRY_JSON = DATA_DIR / "user_registry_cache.json"
GEOCODE_JSON = DATA_DIR / "geocode_cache.json"


def main() -> None:
    imported_registry = 0
    imported_geocode = 0

    if REGISTRY_JSON.is_file():
        payload = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, dict) else []
        if not isinstance(records, list):
            records = []
        sources = payload.get("sources") if isinstance(payload, dict) else []
        source_signature = payload.get("source_signature") if isinstance(payload, dict) else None
        save_user_registry_cache(
            sources=list(sources) if isinstance(sources, list) else [],
            records=records,
            source_signature=str(source_signature or ""),
        )
        imported_registry = len(records)

    if GEOCODE_JSON.is_file():
        payload = json.loads(GEOCODE_JSON.read_text(encoding="utf-8"))
        geocode = payload if isinstance(payload, dict) else {}
        save_geocode_cache(geocode)
        imported_geocode = len(geocode)

    print(f"Imported registry rows: {imported_registry}")
    print(f"Imported geocode rows: {imported_geocode}")


if __name__ == "__main__":
    main()
