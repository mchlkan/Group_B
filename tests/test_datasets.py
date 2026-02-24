import os
import pytest 
import geopandas as gpd

# TODO: update this import once the module is ready
# from src.data_processing import download_datasets, merge_datasets

@pytest.fixture(scope="module")
def downloaded_files():
    download_datasets()
    assert os.path.exists("downloads/"), "downloads/ directory doesn't exist"
    return os.listdir("downloads/")

def test_download_datasets(downloaded_files):
    assert len(downloaded_files) > 0

def test_merge_datasets(downloaded_files):
    result = merge_datasets()
    assert isinstance(result, gpd.GeoDataFrame), "Result is not a GeoDataFrame"

    # TODO: replace with actual expected column names
    expected_columns = ["geometry", "column_a", "column_b"]
    for col in expected_columns:
        assert col in result.columns, f"Missing expected column: {col}"

    assert len(result) > 0, "Merged GeoDataFrame is empty"






