from app.services.registry_import_jobs import _collect_selector_telemetry
from app.services.user_registry_cache import _build_parse_quality_summary


def test_parse_quality_summary_good_verdict() -> None:
    report = {
        "version": "parser-v2.1",
        "stats": {
            "rows_total": 100,
            "owner_empty": 5,
            "address_empty": 1,
            "address_no_locality": 3,
            "phones_empty": 8,
            "object_placeholder": 2,
            "low_confidence": 4,
        },
    }
    summary = _build_parse_quality_summary(report)
    assert summary is not None
    assert summary["verdict"] == "good"
    assert summary["empty_owner_pct"] == 5.0


def test_parse_quality_summary_warn_verdict() -> None:
    report = {
        "version": "parser-v2.1",
        "stats": {
            "rows_total": 100,
            "owner_empty": 35,
            "address_empty": 2,
            "address_no_locality": 5,
            "phones_empty": 10,
            "object_placeholder": 2,
            "low_confidence": 25,
        },
    }
    summary = _build_parse_quality_summary(report)
    assert summary is not None
    assert summary["verdict"] == "warn"
    assert summary["empty_owner_pct"] == 35.0
    assert summary["low_confidence_pct"] == 25.0


def test_parse_quality_summary_includes_selector_telemetry() -> None:
    report = {
        "version": "parser-v2.1",
        "stats": {
            "rows_total": 100,
            "owner_empty": 5,
            "address_empty": 1,
            "address_no_locality": 3,
            "phones_empty": 8,
            "object_placeholder": 2,
            "low_confidence": 4,
        },
        "selector_telemetry": {
            "repair_pass_rows": 10,
            "rows_total": 100,
            "by_field": {
                "owner": {"primary": 6, "alternative": 4, "other": 0},
                "object_name": {"primary": 10, "alternative": 0, "other": 0},
                "phones": {"primary": 8, "alternative": 2, "other": 0},
                "address": {"primary": 7, "alternative": 3, "other": 0},
            },
        },
    }
    summary = _build_parse_quality_summary(report)
    assert summary is not None
    assert summary["repair_pass_rows"] == 10
    assert summary["repair_pass_pct"] == 10.0
    assert summary["repair_owner_alt_pct"] == 40.0
    assert summary["repair_object_alt_pct"] == 0.0
    assert summary["repair_phones_alt_pct"] == 20.0
    assert summary["repair_address_alt_pct"] == 30.0


def test_collect_selector_telemetry_from_parse_notes() -> None:
    rows = [
        {
            "parse_notes": [
                "repair_pass_applied",
                "owner_selected_primary(score:10>5)",
                "object_selected_alternative(score:20>10)",
                "phones_selected_primary_by_length(len:5>=5)",
                "address_selected_alternative(score:30>15)",
            ]
        },
        {"parse_notes": ["address_empty"]},
    ]
    tel = _collect_selector_telemetry(rows)
    assert tel["repair_pass_rows"] == 1
    assert tel["rows_total"] == 2
    assert tel["by_field"]["owner"]["primary"] == 1
    assert tel["by_field"]["object_name"]["alternative"] == 1
    assert tel["by_field"]["phones"]["primary"] == 1
    assert tel["by_field"]["address"]["alternative"] == 1
