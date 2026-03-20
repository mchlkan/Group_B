"""Tests for the OwidData class (Function 1 & Function 2).

Run from the project root with:
    pytest tests/test_datasets.py -v
"""

from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest

from app.data import OwidData


# ── shared fixture ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def data() -> OwidData:
    """Instantiate OwidData once for the whole test module.

    The __init__ method executes Function 1 (download) and
    Function 2 (merge), so every test can inspect the results.
    """
    return OwidData(download_dir="downloads")


# ── Function 1: download_datasets ──────────────────────────────────


def test_downloads_directory_exists(data: OwidData) -> None:
    assert data.download_dir.exists(), "downloads/ directory was not created"


def test_all_csv_files_downloaded(data: OwidData) -> None:
    for name in OwidData.DATASET_URLS:
        filepath = data.download_dir / f"{name}.csv"
        assert filepath.exists(), f"Missing downloaded file: {filepath}"


def test_map_file_downloaded(data: OwidData) -> None:
    map_path = data.download_dir / "ne_110m_admin_0_countries.zip"
    assert map_path.exists(), "Natural Earth shapefile was not downloaded"


def test_datasets_are_dataframes(data: OwidData) -> None:
    for name, df in data.datasets.items():
        assert isinstance(df, pd.DataFrame), f"Dataset '{name}' is not a DataFrame"


def test_datasets_not_empty(data: OwidData) -> None:
    for name, df in data.datasets.items():
        assert len(df) > 0, f"Dataset '{name}' is empty"


# ── Function 2: merge_datasets ─────────────────────────────────────


def test_merged_are_geodataframes(data: OwidData) -> None:
    for name, gdf in data.merged.items():
        assert isinstance(
            gdf, gpd.GeoDataFrame
        ), f"Merged '{name}' is not a GeoDataFrame"


def test_merged_not_empty(data: OwidData) -> None:
    for name, gdf in data.merged.items():
        assert len(gdf) > 0, f"Merged GeoDataFrame '{name}' is empty"


def test_geometry_column_present(data: OwidData) -> None:
    for name, gdf in data.merged.items():
        assert (
            "geometry" in gdf.columns
        ), f"Merged '{name}' is missing a 'geometry' column"


def test_world_is_left_side(data: OwidData) -> None:
    """The world GeoDataFrame must be the left side of the merge,
    so every country geometry from Natural Earth should appear."""
    for name, gdf in data.merged.items():
        assert len(gdf) >= len(data.world), (
            f"Merged '{name}' has fewer rows than the world map – "
            "world should be the left DataFrame in the merge"
        )


# ── Helper methods: value_column ─────────────────────────────────


def test_value_column_returns_string(data: OwidData) -> None:
    for key in data.datasets:
        col = data.value_column(key)
        assert isinstance(col, str)
        assert col in data.datasets[key].columns


def test_value_column_invalid_key_raises(data: OwidData) -> None:
    with pytest.raises(KeyError):
        data.value_column("nonexistent_dataset")


def test_value_column_ambiguous_raises(data: OwidData) -> None:
    """value_column raises ValueError when multiple metric candidates exist."""
    key = next(iter(data.datasets))
    original = data.datasets[key]
    # Inject an extra non-meta column to trigger the guard
    data.datasets[key] = original.assign(extra_metric=0.0)
    try:
        with pytest.raises(ValueError, match="Expected 1 metric column"):
            data.value_column(key)
    finally:
        data.datasets[key] = original


# ── Helper methods: available_years ──────────────────────────────


def test_available_years_returns_sorted_ints(data: OwidData) -> None:
    for key in data.datasets:
        years = data.available_years(key)
        assert isinstance(years, list)
        assert len(years) > 0
        assert years == sorted(years)
        assert all(isinstance(y, int) for y in years)


# ── Helper methods: country_data ─────────────────────────────────


def test_country_data_filters_by_year(data: OwidData) -> None:
    key = next(iter(data.datasets))
    years = data.available_years(key)
    if years:
        year = years[0]
        cdf = data.country_data(key, year)
        assert isinstance(cdf, gpd.GeoDataFrame)
        assert all(cdf["year"] == year)


# ── Helper methods: top_bottom_countries ─────────────────────────


def test_top_bottom_countries_structure(data: OwidData) -> None:
    key = next(iter(data.datasets))
    years = data.available_years(key)
    if years:
        year = years[-1]
        result = data.top_bottom_countries(key, year, n=3)
        assert isinstance(result, pd.DataFrame)
        assert "group" in result.columns
        groups = set(result["group"])
        assert "Top 3" in groups
        assert "Bottom 3" in groups


# ── Helper methods: country_timeseries ───────────────────────────


def test_country_timeseries_returns_sorted(data: OwidData) -> None:
    key = next(iter(data.datasets))
    # Pick an ISO code that exists in the dataset
    df = data.datasets[key]
    mappable = df[df["is_mappable"]]
    if not mappable.empty:
        iso_code = mappable["code"].iloc[0]
        ts = data.country_timeseries(key, iso_code)
        assert isinstance(ts, pd.DataFrame)
        assert len(ts) > 0
        years = ts["year"].tolist()
        assert years == sorted(years)


# ── Helper methods: country_details ──────────────────────────────


def test_country_details_returns_dict(data: OwidData) -> None:
    key = next(iter(data.datasets))
    years = data.available_years(key)
    if years:
        year = years[-1]
        cdf = data.country_data(key, year)
        codes = cdf["code"].dropna()
        if not codes.empty:
            iso = codes.iloc[0]
            details = data.country_details(key, iso, year)
            assert details is not None
            assert "entity" in details
            assert "region" in details
            assert "value" in details
            assert "rank" in details
            assert "delta" in details


def test_country_details_missing_returns_none(data: OwidData) -> None:
    key = next(iter(data.datasets))
    years = data.available_years(key)
    if years:
        result = data.country_details(key, "ZZZ", years[0])
        assert result is None


# ── Download branches (file-not-exists paths) ───────────────────


def test_download_datasets_fetches_when_missing(tmp_path) -> None:
    """Verify download_datasets calls urlopen when CSV does not exist."""
    csv_body = b"entity,code,year,metric\nA,AAA,2020,1.0\n"
    fake_response = MagicMock()
    fake_response.read.return_value = csv_body
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)

    instance = OwidData.__new__(OwidData)
    instance.download_dir = tmp_path
    tmp_path.mkdir(exist_ok=True)

    with patch("urllib.request.urlopen", return_value=fake_response):
        instance.download_datasets()

    for name in OwidData.DATASET_URLS:
        filepath = tmp_path / f"{name}.csv"
        assert filepath.exists()


def test_load_map_fetches_when_missing(tmp_path) -> None:
    """Verify _load_map calls urlopen when shapefile does not exist."""
    # Copy the real shapefile bytes so gpd.read_file works
    from pathlib import Path

    real_path = Path("downloads") / "ne_110m_admin_0_countries.zip"
    if not real_path.exists():
        pytest.skip("shapefile not available locally")

    zip_bytes = real_path.read_bytes()
    fake_response = MagicMock()
    fake_response.read.return_value = zip_bytes
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)

    instance = OwidData.__new__(OwidData)
    instance.download_dir = tmp_path
    tmp_path.mkdir(exist_ok=True)

    with patch("urllib.request.urlopen", return_value=fake_response):
        result = instance._load_map()

    assert isinstance(result, gpd.GeoDataFrame)
    assert (tmp_path / "ne_110m_admin_0_countries.zip").exists()
