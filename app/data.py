"""Data handling for Project Okavango.

This module contains the OwidData class that downloads, cleans, and
merges environmental datasets from Our World in Data with Natural Earth
country geometries.

"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Mapping, Set
import geopandas as gpd
import pandas as pd
import urllib.request


# Defining the OwidData class

class OwidData:
    """Download, preprocess, and merge OWID environmental datasets.

    On initialisation the class executes the full data pipeline:
        1. Download all CSV datasets and the Natural Earth shapefile
           into *download_dir*.
        2. Preprocess every dataset via
           :meth:`preprocess_datasets`.
        3. Merge each preprocessed dataset with the Natural Earth
           world map.

    The resulting GeoDataFrames are stored as instance attributes
    and can be consumed directly by the Streamlit front-end.

    Attributes
    ----------
    download_dir : Path
        Directory where downloaded files are stored.
    world : gpd.GeoDataFrame
        Natural Earth country geometries.
    datasets : Dict[str, pd.DataFrame]
        Preprocessed OWID datasets keyed by name.
    merged : Dict[str, gpd.GeoDataFrame]
        Datasets merged with world geometries, keyed by name.
    """

    # Defining class constants

    DATASET_LABELS: Dict[str, str] = {
        "forest_change": "Annual Change in Forest Area",
        "deforestation": "Annual Deforestation",
        "land_protected": "Share of Protected Land",
        "land_degraded": "Share of Degraded Land",
        "marine_protected": "Share of Marine Protected Areas",
    }
    """Human-readable labels for each dataset key."""

    DATASET_URLS: Dict[str, str] = {
        "forest_change": (
            "https://ourworldindata.org/grapher/"
            "forest-area-net-change-rate.csv"
            "?v=1&csvType=full&useColumnShortNames=true"
        ),
        "deforestation": (
            "https://ourworldindata.org/grapher/"
            "annual-deforestation.csv"
            "?v=1&csvType=full&useColumnShortNames=true"
        ),
        "land_protected": (
            "https://ourworldindata.org/grapher/"
            "terrestrial-protected-areas.csv"
            "?v=1&csvType=full&useColumnShortNames=true"
        ),
        "land_degraded": (
            "https://ourworldindata.org/grapher/"
            "share-degraded-land.csv"
            "?v=1&csvType=full&useColumnShortNames=true"
        ),
        "marine_protected": (
            "https://ourworldindata.org/grapher/"
            "marine-protected-areas.csv"
            "?v=1&csvType=full&useColumnShortNames=true"
        ),
    }
    """URLs for the five OWID environmental datasets."""

    MAP_URL: str = (
        "https://naciscdn.org/naturalearth/"
        "110m/cultural/ne_110m_admin_0_countries.zip"
    )
    """URL for the Natural Earth 110 m country shapefile."""

    META_COLS: Set[str] = {"entity", "code", "year"}
    """Column names present in every OWID dataset that are not value columns."""

    KNOWN_NON_METRIC: Set[str] = {
        "entity", "code", "year", "is_aggregate", "is_mappable",
    }
    """Columns to exclude when auto-detecting the single metric column."""

    # Initialisation

    def __init__(self, download_dir: str = "downloads") -> None:
        """Initialise the data pipeline.

        Parameters
        ----------
        download_dir : str, optional
            Path to the directory used for storing downloaded files.
            Created automatically if it does not exist.
            Defaults to ``"downloads"``.
        """
        self.download_dir: Path = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

        # Function 1: Downloading datasets and map
        raw_datasets: Dict[str, pd.DataFrame] = self.download_datasets()

        # Preprocessing the datasets before merging
        self.datasets: Dict[str, pd.DataFrame] = (
            self.preprocess_datasets(raw_datasets)
        )

        # Loading the Natural Earth world map
        self.world: gpd.GeoDataFrame = self._load_map()

        # Function 2 — merging datasets with the world map
        self.merged: Dict[str, gpd.GeoDataFrame] = self.merge_datasets()

    # Defining function 1: Downloading datasets and map

    def download_datasets(self) -> Dict[str, pd.DataFrame]:
        """Download all OWID CSV datasets into the downloads directory.

        Files that already exist locally are not re-downloaded.

        Returns
        -------
        Dict[str, pd.DataFrame]
            Dictionary mapping dataset names to raw DataFrames.
        """
        headers: Dict[str, str] = {"User-Agent": "Mozilla/5.0"}
        datasets: Dict[str, pd.DataFrame] = {}

        for name, url in self.DATASET_URLS.items():
            filepath: Path = self.download_dir / f"{name}.csv"

            if not filepath.exists():
                req = urllib.request.Request(url, headers=headers)
                with (
                    urllib.request.urlopen(req) as response,
                    open(filepath, "wb") as out_file,
                ):
                    out_file.write(response.read())

            datasets[name] = pd.read_csv(filepath)

        return datasets

    # Defining function to load map

    def _load_map(self) -> gpd.GeoDataFrame:
        """Download (if needed) and load the Natural Earth world map.

        Returns
        -------
        gpd.GeoDataFrame
            Country-level geometries with ISO codes and metadata.
        """
        map_path: Path = self.download_dir / "ne_110m_admin_0_countries.zip"

        if not map_path.exists():
            headers: Dict[str, str] = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(self.MAP_URL, headers=headers)
            with (
                urllib.request.urlopen(req) as response,
                open(map_path, "wb") as out_file,
            ):
                out_file.write(response.read())

        return gpd.read_file(map_path)

    # Defining function to preprocess datasets

    def preprocess_datasets(
        self,
        datasets: Mapping[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """Preprocess raw OWID datasets for analysis and merging.

        Each OWID dataset follows a long format with base columns
        ``entity``, ``code``, ``year`` and exactly one numeric metric
        column whose name varies per dataset.

        Processing steps applied to every dataset:
            1. Validate that required base columns are present.
            2. Auto-detect the single metric column.
            3. Enforce dtypes (``year`` → ``Int64``, metric → ``float``).
            4. Drop duplicate rows on the composite key
               (``entity``, ``code``, ``year``).
            5. Add boolean flags:
               - ``is_aggregate``: ``True`` when ``code`` is missing or
                 starts with ``OWID_``.
               - ``is_mappable``: ``True`` when the row carries a valid
                 three-letter ISO Alpha-3 code suitable for a GeoPandas
                 merge.
            6. Sort deterministically and reset the index.

        Aggregate rows and statistical outliers are intentionally kept.

        Parameters
        ----------
        datasets : Mapping[str, pd.DataFrame]
            Dictionary mapping dataset names to raw OWID DataFrames.

        Returns
        -------
        Dict[str, pd.DataFrame]
            Dictionary mapping dataset names to cleaned DataFrames.

        Raises
        ------
        TypeError
            If a value in *datasets* is not a DataFrame.
        ValueError
            If required columns are missing or metric column detection
            is ambiguous.
        """
        cleaned: Dict[str, pd.DataFrame] = {}

        for name, df in datasets.items():
            # --- input validation ---
            if not isinstance(df, pd.DataFrame):
                raise TypeError(
                    f"Dataset '{name}' must be a pandas DataFrame, "
                    f"got {type(df)!r}."
                )

            missing = self.META_COLS - set(df.columns)
            if missing:
                raise ValueError(
                    f"Dataset '{name}' is missing required columns: "
                    f"{sorted(missing)}."
                )

            out = df.copy(deep=True)

            # --- auto-detect the metric column ---
            metric_candidates = [
                col for col in out.columns
                if col not in self.KNOWN_NON_METRIC
            ]

            if len(metric_candidates) != 1:
                raise ValueError(
                    f"Dataset '{name}': expected exactly 1 metric "
                    f"column besides {sorted(self.META_COLS)}, found "
                    f"{len(metric_candidates)}: {metric_candidates}."
                )

            metric_col: str = metric_candidates[0]

            # --- enforce dtypes ---
            out["year"] = (
                pd.to_numeric(out["year"], errors="coerce")
                .astype("Int64")
            )
            out[metric_col] = (
                pd.to_numeric(out[metric_col], errors="coerce")
                .astype(float)
            )

            # --- boolean flags ---
            code_str = out["code"].astype("string")

            out["is_aggregate"] = (
                out["code"].isna()
                | code_str.str.startswith("OWID_", na=False)
            )

            iso_like = code_str.str.fullmatch(
                r"[A-Za-z]{3}", na=False,
            )
            out["is_mappable"] = ~out["is_aggregate"] & iso_like

            # --- deduplicate on composite key ---
            out = out.drop_duplicates(
                subset=["entity", "code", "year"],
                keep="first",
            )

            # --- deterministic sort ---
            out = (
                out
                .sort_values(
                    by=["is_aggregate", "code", "entity", "year"],
                    na_position="last",
                    kind="mergesort",
                )
                .reset_index(drop=True)
            )

            cleaned[name] = out

        return cleaned

    # Defining function 2: Merging datasets with the world map

    def merge_datasets(self) -> Dict[str, gpd.GeoDataFrame]:
        """Merge each preprocessed dataset with the Natural Earth world map.

        Only rows flagged as ``is_mappable`` are included in the merge.
        The world GeoDataFrame is always the left side of the join,
        as required by the assignment specification.

        The merge key is ``ISO_A3_EH`` (Natural Earth) ↔ ``code``
        (OWID), chosen because ``ISO_A3_EH`` has fewer missing values
        than ``ISO_A3`` (see EDA notebook, section 8).

        Returns
        -------
        Dict[str, gpd.GeoDataFrame]
            Dictionary mapping dataset names to merged GeoDataFrames.
        """
        merged: Dict[str, gpd.GeoDataFrame] = {}

        for name, df in self.datasets.items():
            mappable: pd.DataFrame = df[df["is_mappable"]].copy()

            merged_gdf: gpd.GeoDataFrame = self.world.merge(
                mappable,
                left_on="ISO_A3_EH",
                right_on="code",
                how="left",
            )

            merged[name] = merged_gdf

        return merged

    # ------------------------------------------------------------------ #
    #  Helper methods for the Streamlit front-end                         #
    # ------------------------------------------------------------------ #

    def value_column(self, key: str) -> str:
        """Return the single metric column name for a dataset.

        Auto-detects the column by excluding all known non-metric
        columns, so that the Streamlit layer never needs to hardcode
        OWID column names.

        Parameters
        ----------
        key : str
            Dataset key (e.g. ``"forest_change"``).

        Returns
        -------
        str
            Name of the metric column.

        Raises
        ------
        KeyError
            If *key* is not a valid dataset name.
        ValueError
            If detection fails (zero or multiple candidates).
        """
        df: pd.DataFrame = self.datasets[key]
        candidates = [
            c for c in df.columns if c not in self.KNOWN_NON_METRIC
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Expected 1 metric column in '{key}', "
                f"found {len(candidates)}: {candidates}."
            )
        return candidates[0]

    def available_years(self, key: str) -> list[int]:
        """Return sorted unique years with mappable data for *key*.

        Only considers rows that have a non-null metric value and a
        valid geometry in the merged GeoDataFrame, so the Streamlit
        year slider only offers years where the map can be drawn.

        Parameters
        ----------
        key : str
            Dataset key.

        Returns
        -------
        list[int]
            Sorted list of available years.
        """
        gdf: gpd.GeoDataFrame = self.merged[key]
        val_col: str = self.value_column(key)
        valid = gdf.dropna(subset=[val_col, "geometry"])
        years = sorted(valid["year"].dropna().unique().tolist())
        return [int(y) for y in years]

    def country_data(
        self, key: str, year: int,
    ) -> gpd.GeoDataFrame:
        """Return map-ready country data for a single year.

        Filters ``self.merged[key]`` to the requested *year* and drops
        rows with missing metric values or geometries.

        Parameters
        ----------
        key : str
            Dataset key.
        year : int
            Year to filter to.

        Returns
        -------
        gpd.GeoDataFrame
            Filtered GeoDataFrame suitable for ``px.choropleth``.
        """
        gdf: gpd.GeoDataFrame = self.merged[key]
        val_col: str = self.value_column(key)
        filtered = gdf[gdf["year"] == year].dropna(
            subset=[val_col, "geometry"],
        )
        return filtered.copy()

    def top_bottom_countries(
        self, key: str, year: int, n: int = 5,
    ) -> pd.DataFrame:
        """Return the *n* highest and *n* lowest countries for a year.

        Parameters
        ----------
        key : str
            Dataset key.
        year : int
            Year to evaluate.
        n : int, optional
            Number of top and bottom entries (default ``5``).

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ``entity``, ``code``, the metric
            column, ``REGION_UN``, and a ``group`` label
            (``"Top {n}"`` / ``"Bottom {n}"``).
        """
        cdf: gpd.GeoDataFrame = self.country_data(key, year)
        val_col: str = self.value_column(key)
        keep_cols = ["entity", "code", val_col, "REGION_UN"]
        available = [c for c in keep_cols if c in cdf.columns]
        cdf_slim = cdf[available].copy()

        top = cdf_slim.nlargest(n, val_col)
        bottom = cdf_slim.nsmallest(n, val_col)

        top = top.copy()
        bottom = bottom.copy()
        top["group"] = f"Top {n}"
        bottom["group"] = f"Bottom {n}"

        result = pd.concat([top, bottom], ignore_index=True)
        return result

    def country_timeseries(
        self, key: str, iso_code: str,
    ) -> pd.DataFrame:
        """Return the full time series for one country.

        Uses ``self.datasets[key]`` (which includes all years) rather
        than the merged GeoDataFrame, for completeness.

        Parameters
        ----------
        key : str
            Dataset key.
        iso_code : str
            Three-letter ISO Alpha-3 country code.

        Returns
        -------
        pd.DataFrame
            Rows for the requested country sorted by year.
        """
        df: pd.DataFrame = self.datasets[key]
        mask = (df["is_mappable"]) & (df["code"] == iso_code)
        result = df.loc[mask].sort_values("year").reset_index(drop=True)
        return result

    def country_details(
        self,
        key: str,
        iso_code: str,
        year: int,
    ) -> Dict[str, object] | None:
        """Return summary details for one country in a given year.

        Parameters
        ----------
        key : str
            Dataset key.
        iso_code : str
            Three-letter ISO Alpha-3 country code.
        year : int
            Year of interest.

        Returns
        -------
        dict or None
            Dictionary with keys ``entity``, ``region``, ``value``,
            ``rank``, and ``delta`` (change vs. previous year).
            Returns ``None`` when no data is found.
        """
        val_col: str = self.value_column(key)
        cdf: gpd.GeoDataFrame = self.country_data(key, year)

        row = cdf[cdf["code"] == iso_code]
        if row.empty:
            return None

        row = row.iloc[0]
        entity: str = str(row.get("entity", iso_code))
        region: str = str(row.get("REGION_UN", "Unknown"))
        value: float = float(row[val_col])

        # Rank (1 = highest value)
        ranked = cdf[val_col].rank(ascending=False, method="min")
        rank: int = int(
            ranked[cdf["code"] == iso_code].iloc[0]
        )

        # Delta vs previous year
        ts = self.country_timeseries(key, iso_code)
        prev = ts[ts["year"] == year - 1]
        delta: float | None = None
        if not prev.empty:
            delta = value - float(prev.iloc[0][val_col])

        return {
            "entity": entity,
            "region": region,
            "value": value,
            "rank": rank,
            "delta": delta,
        }