"""Tests for app.database — cache lookup, error paths, and return structure."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

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


def test_insert_failure_returns_false(tmp_path, monkeypatch):
    """insert_analysis returns False on sqlite3.Error."""
    _use_tmp_db(tmp_path, monkeypatch)

    with patch("sqlite3.connect", side_effect=sqlite3.Error("disk full")):
        result = database.insert_analysis(
            10.0, 20.0, 5, "img.jpg", _sample_analysis()
        )
    assert result is False


def test_lookup_failure_returns_none(tmp_path, monkeypatch):
    """lookup_analysis returns None on sqlite3.Error."""
    _use_tmp_db(tmp_path, monkeypatch)

    with patch("sqlite3.connect", side_effect=sqlite3.Error("locked")):
        result = database.lookup_analysis(10.0, 20.0, 5)
    assert result is None


def test_lookup_returns_full_structure(tmp_path, monkeypatch):
    """Verify the returned dict has the expected nested structure."""
    _use_tmp_db(tmp_path, monkeypatch)

    analysis = _sample_analysis()
    database.insert_analysis(
        38.88, -9.25, 14, "images/test.jpg", analysis
    )

    cached = database.lookup_analysis(38.88, -9.25, 14)
    assert cached is not None
    assert cached["image_path"] == "images/test.jpg"
    assert cached["latitude"] == 38.88
    assert cached["longitude"] == -9.25
    assert cached["zoom"] == 14
    assert cached["analysis"]["description"] == "Test description"
    assert cached["analysis"]["danger_level"] == 2
    assert cached["analysis"]["danger_label"] == "Low"
    assert cached["analysis"]["danger_reason"] == "No visible damage."


def test_lookup_no_match_returns_none(tmp_path, monkeypatch):
    """lookup_analysis returns None when no matching row exists."""
    _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    result = database.lookup_analysis(99.0, 99.0, 1)
    assert result is None
