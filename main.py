"""Project Okavango — Streamlit application.

This module builds the interactive Streamlit dashboard for
environmental data analysis.  It imports the ``OwidData`` class from
``app.data`` and uses its helper methods to populate maps, charts,
KPIs, and detail panels.

Run with::

    streamlit run main.py
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd
import plotly.express as px
import streamlit as st

from app.data import OwidData


class ViewContext(NamedTuple):
    """Bundle of values shared across rendering helpers."""

    selected_key: str
    selected_year: int
    val_col: str
    label: str
    sel_key: str

# ------------------------------------------------------------------ #
#  Data loading (cached so it only runs once per session)             #
# ------------------------------------------------------------------ #


@st.cache_resource
def load_data() -> OwidData:
    """Instantiate and cache the data manager."""
    return OwidData()


# ------------------------------------------------------------------ #
#  UI helper functions                                                 #
# ------------------------------------------------------------------ #


def _extract_click(event: object) -> str | None:
    """Extract the ISO code from a Plotly selection event.

    Parameters
    ----------
    event : object
        The value returned by ``st.plotly_chart`` with
        ``on_select="rerun"``.

    Returns
    -------
    str or None
        ISO Alpha-3 code if a valid click was detected, else ``None``.

    """
    if (
        event
        and isinstance(event, dict)
        and "selection" in event
        and event["selection"].get("points")
    ):
        point = event["selection"]["points"][0]
        custom = point.get("customdata")
        if custom:
            return str(custom[0])
    return None


def _render_kpis(gdf: pd.DataFrame, val_col: str) -> None:
    """Display a row of four KPI metric cards.

    Parameters
    ----------
    gdf : pd.DataFrame
        Year-filtered country GeoDataFrame.
    val_col : str
        Name of the metric column.

    """
    st.subheader("Key indicators")
    valid = gdf[val_col].dropna()
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        st.metric("Countries with data", len(valid))
    with kpi2:
        st.metric(
            "Global mean",
            f"{valid.mean():.2f}" if len(valid) else "N/A",
        )
    with kpi3:
        if len(valid):
            idx = valid.idxmax()
            st.metric(
                "Highest",
                f"{valid.max():.2f}",
                delta=str(gdf.loc[idx, "entity"]),
            )
        else:
            st.metric("Highest", "N/A")
    with kpi4:
        if len(valid):
            idx = valid.idxmin()
            st.metric(
                "Lowest",
                f"{valid.min():.2f}",
                delta=str(gdf.loc[idx, "entity"]),
            )
        else:
            st.metric("Lowest", "N/A")


def _render_bar_chart(data: OwidData, ctx: ViewContext) -> None:
    """Display the top-5 / bottom-5 comparative bar chart.

    Parameters
    ----------
    data : OwidData
        Initialised data manager.
    ctx : ViewContext
        Current view parameters.

    """
    st.subheader("Global Trend")
    chart_data = data.top_bottom_countries(
        ctx.selected_key, ctx.selected_year,
    )

    if chart_data.empty:
        st.info("No country data available for this year.")
        return

    bar_fig = px.bar(
        chart_data,
        x="entity",
        y=ctx.val_col,
        color="group",
        custom_data=["code"],
        title=f"Top and bottom 5 countries — {ctx.label}",
        labels={
            "entity": "Country",
            ctx.val_col: ctx.label,
            "group": "Group",
        },
        color_discrete_map={
            "Top 5": "#4ade80",
            "Bottom 5": "#f87171",
        },
    )
    bar_fig.update_layout(
        height=360,
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        xaxis_title="Country",
        yaxis_title=ctx.label,
    )

    bar_event = st.plotly_chart(
        bar_fig,
        on_select="rerun",
        selection_mode="points",
        key=f"bar_{ctx.selected_key}_{ctx.selected_year}",
        width="stretch",
    )

    clicked = _extract_click(bar_event)
    if clicked:
        st.session_state[ctx.sel_key] = clicked
        st.rerun()


def _render_details_and_trend(
    data: OwidData, ctx: ViewContext,
) -> None:
    """Display the country-detail panel and trend line chart.

    Parameters
    ----------
    data : OwidData
        Initialised data manager.
    ctx : ViewContext
        Current view parameters.

    """
    selected_code: str | None = st.session_state[ctx.sel_key]
    details_col, trend_col = st.columns([1, 2], gap="large")

    with details_col:
        st.subheader("Selection details")
        if selected_code is None:
            st.info("Click a country on the map or bar chart.")
        else:
            details = data.country_details(
                ctx.selected_key, selected_code, ctx.selected_year,
            )
            if details is None:
                st.warning(
                    "No data for this country in the selected "
                    "dataset / year.",
                )
            else:
                st.metric("Country", details["entity"])
                st.metric("Region", details["region"])
                st.metric(ctx.label, f"{details['value']:.2f}")
                st.metric("Rank", f"#{details['rank']}")
                delta = details["delta"]
                st.metric(
                    "Change vs. prev. year",
                    f"{details['value']:.2f}",
                    delta=(
                        "N/A"
                        if delta is None
                        else f"{delta:+.2f}"
                    ),
                )

    with trend_col:
        st.subheader("Trend")
        if selected_code is None:
            st.info("Trend appears after selecting a country.")
        else:
            trend = data.country_timeseries(
                ctx.selected_key, selected_code,
            )
            trend = trend[trend["year"] <= ctx.selected_year]
            if trend.empty:
                st.warning("No time-series data for this country.")
            else:
                trend_fig = px.line(
                    trend,
                    x="year",
                    y=ctx.val_col,
                    markers=True,
                    title=f"{trend['entity'].iloc[0]} · {ctx.label}",
                    labels={
                        "year": "Year",
                        ctx.val_col: ctx.label,
                    },
                )
                trend_fig.update_layout(
                    height=320,
                    margin={"l": 0, "r": 0, "t": 45, "b": 0},
                )
                st.plotly_chart(trend_fig, width="stretch")


# ------------------------------------------------------------------ #
#  Main application                                                    #
# ------------------------------------------------------------------ #


def main() -> None:
    """Entry point for the Streamlit app."""
    st.set_page_config(page_title="Project Okavango", layout="wide")
    st.title("Project Okavango")
    st.caption("Environmental analysis with latest available OWID data")

    data = load_data()

    # ── Sidebar controls ──────────────────────────────────────────── #
    with st.sidebar:
        st.header("Controls")

        selected_key: str = st.selectbox(
            "Dataset",
            options=list(OwidData.DATASET_LABELS.keys()),
            format_func=lambda k: OwidData.DATASET_LABELS[k],
        )

        years = data.available_years(selected_key)
        selected_year: int = st.select_slider(
            "Year",
            options=years,
            value=years[-1] if years else None,
        )

        # Region filter based on Natural Earth REGION_UN column
        gdf = data.country_data(selected_key, selected_year)
        all_regions: list[str] = sorted(
            gdf["REGION_UN"].dropna().unique().tolist(),
        )
        selected_regions: list[str] = st.multiselect(
            "Filter by region",
            options=all_regions,
            default=all_regions,
        )

    # ── Apply region filter ───────────────────────────────────────── #
    if selected_regions and selected_regions != all_regions:
        gdf = gdf[gdf["REGION_UN"].isin(selected_regions)]

    val_col: str = data.value_column(selected_key)
    label: str = OwidData.DATASET_LABELS[selected_key]

    # ── Session state for country selection ────────────────────────── #
    sel_key = f"sel::{selected_key}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = None

    # ── KPI row ───────────────────────────────────────────────────── #
    _render_kpis(gdf, val_col)

    # ── Choropleth world map ──────────────────────────────────────── #
    st.subheader(f"{label} ({selected_year})")

    map_fig = px.choropleth(
        gdf,
        locations="code",
        color=val_col,
        hover_name="entity",
        hover_data={"code": True, val_col: ":.2f", "REGION_UN": True},
        custom_data=["code"],
        locationmode="ISO-3",
        color_continuous_scale="Tealgrn",
        title="Click a country to inspect details",
        labels={
            val_col: label,
            "code": "ISO Code",
            "REGION_UN": "Region",
        },
    )
    map_fig.update_layout(
        height=520,
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )

    map_event = st.plotly_chart(
        map_fig,
        on_select="rerun",
        selection_mode="points",
        key=f"map_{selected_key}_{selected_year}",
        width="stretch",
    )

    clicked = _extract_click(map_event)
    if clicked:
        st.session_state[sel_key] = clicked

    ctx = ViewContext(
        selected_key=selected_key,
        selected_year=selected_year,
        val_col=val_col,
        label=label,
        sel_key=sel_key,
    )

    # ── Country detail panel + trend line ─────────────────────────── #
    _render_details_and_trend(data, ctx)

    # ── Global trend (top 5 / bottom 5) ──────────────────────────── #
    _render_bar_chart(data, ctx)


if __name__ == "__main__":
    main()
