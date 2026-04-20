from app.services.registry_import_jobs import _is_address_geocode_candidate


def test_address_geocode_candidate_accepts_real_address() -> None:
    assert _is_address_geocode_candidate("223034, г. Заславль, ул. Советская, 133")


def test_address_geocode_candidate_rejects_placeholder() -> None:
    assert not _is_address_geocode_candidate("не указано")
    assert not _is_address_geocode_candidate("—")
    assert not _is_address_geocode_candidate("abc")
