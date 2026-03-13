"""Tests for app.database cache lookup behavior."""

from __future__ import annotations

from app import database


def _sample_analysis() -> dict:
    return {
        "description": "Test description",
        "image_prompt": "test-image-prompt",
        "image_model": "test-image-model",
        "text_description": "Test risk text",
        "text_prompt": "test-text-prompt",
        "text_model": "test-text-model",
        "danger_level": 2,
        "danger_label": "Low",
        "danger_reason": "No visible damage.",
    }


def _use_tmp_db(tmp_path, monkeypatch) -> None:
    db_dir = tmp_path / "database"
    db_path = db_dir / "okavango.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)


def test_lookup_matches_coordinates_at_three_decimals(tmp_path, monkeypatch):
    """Coordinates that round to the same 3 decimals should hit cache."""
    _use_tmp_db(tmp_path, monkeypatch)

    inserted = database.insert_analysis(
        latitude=38.8801,
        longitude=-9.25,
        zoom=14,
        image_path="images/esri_38.8801_-9.2500_z14.jpg",
        analysis=_sample_analysis(),
    )
    assert inserted is True

    cached = database.lookup_analysis(38.8804, -9.2504, 14)
    assert cached is not None
    assert cached["latitude"] == 38.8801
    assert cached["longitude"] == -9.25
    assert cached["zoom"] == 14


def test_lookup_requires_exact_zoom_match(tmp_path, monkeypatch):
    """Lookup should reuse rows only when zoom matches exactly."""
    _use_tmp_db(tmp_path, monkeypatch)

    database.insert_analysis(
        latitude=38.678,
        longitude=-9.322,
        zoom=16,
        image_path="images/esri_38.6780_-9.3220_z16.jpg",
        analysis=_sample_analysis(),
    )

    hit = database.lookup_analysis(38.678, -9.322, 16)
    miss = database.lookup_analysis(38.678, -9.322, 15)

    assert hit is not None
    assert miss is None
