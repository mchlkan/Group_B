"""Tests for OwidData.preprocess_datasets — covers cleaning, flags, and guards."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data import DatasetMeta, OwidData


def _make_df(
    entities=("A", "B", "C"),
    codes=("AAA", "BBB", "CCC"),
    years=(2020, 2021, 2022),
    values=(1.0, 2.0, 3.0),
    metric_name="metric_value",
):
    """Build a minimal OWID-shaped DataFrame for testing."""
    return pd.DataFrame(
        {
            "entity": list(entities),
            "code": list(codes),
            "year": list(years),
            metric_name: list(values),
        }
    )


class TestDuplicateRemoval:
    def test_duplicates_dropped(self):
        df = _make_df(
            entities=("A", "A", "B"),
            codes=("AAA", "AAA", "BBB"),
            years=(2020, 2020, 2021),
            values=(1.0, 99.0, 2.0),
        )
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        key_rows = result[
            (result["entity"] == "A")
            & (result["code"] == "AAA")
            & (result["year"] == 2020)
        ]
        assert len(key_rows) == 1
        assert key_rows.iloc[0]["metric_value"] == 1.0


class TestMissingValueHandling:
    def test_nan_metric_rows_dropped(self):
        df = _make_df(values=(1.0, float("nan"), 3.0))
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert len(result) == 2
        assert result["metric_value"].isna().sum() == 0

    def test_non_numeric_metric_coerced_and_dropped(self):
        df = pd.DataFrame(
            {
                "entity": ["A", "B"],
                "code": ["AAA", "BBB"],
                "year": [2020, 2021],
                "metric_value": [1.0, "not_a_number"],
            }
        )
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert len(result) == 1


class TestOutlierFlagging:
    def test_extreme_value_flagged(self):
        values = [10.0] * 20 + [10000.0]
        entities = [f"E{i}" for i in range(21)]
        codes = [f"A{chr(65 + i % 26)}{chr(65 + i // 26)}" for i in range(21)]
        years = list(range(2000, 2021))
        df = _make_df(
            entities=entities,
            codes=codes,
            years=years,
            values=values,
        )
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert "is_outlier" in result.columns
        outliers = result[result["is_outlier"]]
        assert len(outliers) >= 1
        assert outliers.iloc[0]["metric_value"] == 10000.0

    def test_normal_values_not_flagged(self):
        df = _make_df(values=(10.0, 11.0, 12.0))
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert result["is_outlier"].sum() == 0


class TestIsAggregateFlag:
    def test_owid_prefix(self):
        df = _make_df(
            entities=("World", "A", "B"),
            codes=("OWID_WRL", "AAA", "BBB"),
        )
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        world_rows = result[result["entity"] == "World"]
        assert bool(world_rows.iloc[0]["is_aggregate"]) is True

    def test_null_code(self):
        df = _make_df(codes=(None, "AAA", "BBB"))
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        null_rows = result[result["code"].isna()]
        assert all(null_rows["is_aggregate"])


class TestIsMappableFlag:
    def test_valid_iso_code(self):
        df = _make_df(codes=("USA", "GBR", "DEU"))
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert all(result["is_mappable"])

    def test_invalid_code_not_mappable(self):
        df = _make_df(
            entities=("A", "B"),
            codes=("OWID_WRL", "12"),
            years=(2020, 2021),
            values=(1.0, 2.0),
        )
        result = OwidData.preprocess_datasets(
            OwidData.__new__(OwidData), {"test": df}
        )["test"]
        assert not any(result["is_mappable"])


class TestDatasetMetaValidation:
    def test_valid_meta(self):
        meta = DatasetMeta(url="https://example.com/data.csv", label="Test")
        assert meta.url == "https://example.com/data.csv"
        assert meta.label == "Test"

    def test_missing_field_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DatasetMeta(url="https://example.com/data.csv")  # type: ignore[call-arg]

    def test_dataset_meta_drives_class_attrs(self):
        for key, meta in OwidData.DATASET_META.items():
            assert isinstance(meta, DatasetMeta)
            assert OwidData.DATASET_URLS[key] == meta.url
            assert OwidData.DATASET_LABELS[key] == meta.label


class TestInputValidation:
    def test_non_dataframe_raises_type_error(self):
        with pytest.raises(TypeError, match="must be a pandas DataFrame"):
            OwidData.preprocess_datasets(
                OwidData.__new__(OwidData), {"test": "not a dataframe"}
            )

    def test_missing_columns_raises_value_error(self):
        df = pd.DataFrame({"entity": ["A"], "year": [2020], "value": [1.0]})
        with pytest.raises(ValueError, match="missing required columns"):
            OwidData.preprocess_datasets(
                OwidData.__new__(OwidData), {"test": df}
            )
