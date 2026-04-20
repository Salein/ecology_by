from __future__ import annotations

from app.services.belarus_locality_centroids import approx_coords_from_locality_in_address
from app.services.object_search import _resolve_coords_for_distance


def test_locality_extract_handles_city_with_trailing_service_text() -> None:
    addr = (
        "246017, ул. Красноармейская, 28, г. Гомель получения вторичного сырья "
        "в районе аг. Вейно, Могилевская область"
    )
    pair = approx_coords_from_locality_in_address(addr)
    assert pair is not None
    la, lo = pair
    # Центр Гомеля.
    assert abs(la - 52.4345) < 0.2
    assert abs(lo - 30.9754) < 0.2


def test_distance_resolver_prefers_city_marker_over_bad_row_coords() -> None:
    row = {
        "id": 3679,
        "owner": "ОАО Дорожно-строительный трест №2, г. Гомель",
        "object_name": "Мобильная установка",
        "address": "246017, ул. Красноармейская, 28, г. Гомель получения вторичного сырья",
        # Условно «битые» координаты в районе Ракова/Минска.
        "lat": 53.96,
        "lon": 27.05,
    }
    la, lo, approx = _resolve_coords_for_distance(row, {})
    assert la is not None and lo is not None
    assert approx is True
    # Должно переключиться на ориентир Гомеля, а не оставить «битые» coords.
    assert abs(la - 52.4345) < 0.25
    assert abs(lo - 30.9754) < 0.25
