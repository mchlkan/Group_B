"""Tests for the OwidData class (Function 1 & Function 2).

Run from the project root with:
    pytest tests/test_datasets.py -v
"""

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
