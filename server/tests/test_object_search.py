from __future__ import annotations

from app.schemas import ObjectSearchRequest
from app.services import object_search as search


def test_search_without_location_returns_limited_unique(monkeypatch) -> None:
    rows = [
        {
            "id": 1,
            "source_part": 1,
            "owner": "A",
            "object_name": "Obj 1",
            "waste_code": "100",
            "waste_type_name": "Type",
            "accepts_external_waste": True,
            "address": "addr 1",
            "phones": "1",
        },
        {
            "id": 1,  # duplicate row key
            "source_part": 1,
            "owner": "A",
            "object_name": "Obj 1",
            "waste_code": "100",
            "waste_type_name": "Type",
            "accepts_external_waste": True,
            "address": "addr 1",
            "phones": "1",
        },
        {
            "id": 2,
            "source_part": 1,
            "owner": "B",
            "object_name": "Obj 2",
            "waste_code": "200",
            "waste_type_name": "Type",
            "accepts_external_waste": True,
            "address": "addr 2",
            "phones": "2",
        },
        {
            "id": 3,
            "source_part": 1,
            "owner": "C",
            "object_name": "Obj 3",
            "waste_code": "300",
            "waste_type_name": "Type",
            "accepts_external_waste": True,
            "address": "addr 3",
            "phones": "3",
        },
    ]
    monkeypatch.setattr(search, "load_search_records", lambda accepts_external_only=False: rows)
    monkeypatch.setattr(search.settings, "registry_closest_limit", 2)

    out = search.run_object_search(ObjectSearchRequest(query=""))

    assert len(out.items) == 2
    assert [item.id for item in out.items] == [1, 2]


def test_search_with_location_uses_adaptive_osrm_candidates(monkeypatch) -> None:
    rows = [
        {
            "id": i,
            "source_part": 1,
            "owner": f"O{i}",
            "object_name": f"Obj {i}",
            "waste_code": f"{i:07d}",
            "waste_type_name": "Type",
            "accepts_external_waste": True,
            "address": f"addr {i}",
            "phones": "",
            "lat": None,
            "lon": None,
        }
        for i in range(1, 701)
    ]
    monkeypatch.setattr(search, "load_search_records", lambda accepts_external_only=True: rows)
    monkeypatch.setattr(search, "load_geocode_cache_subset", lambda keys: {})
    monkeypatch.setattr(search, "_start_async_geocache_warmup", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        search,
        "_resolve_coords_for_distance",
        lambda row, geocache: (53.9 + row["id"] * 0.00001, 27.56, False),
    )

    calls = {"n": 0}

    def _fake_road(ulat, ulon, la, lo, *, client=None):
        calls["n"] += 1
        return 10.0, None

    monkeypatch.setattr(search, "_road_distance_km", _fake_road)
    monkeypatch.setattr(search.settings, "registry_closest_limit", 7)
    monkeypatch.setattr(search.settings, "road_distance_candidates", 25)
    monkeypatch.setattr(search.settings, "distance_mode", "road")

    out = search.run_object_search(ObjectSearchRequest(query="", lat=53.9, lon=27.56))

    # Для больших выборок (700) адаптивный лимит должен урезать OSRM-кандидаты до 18.
    assert calls["n"] == 18
    assert len(out.items) == 7
