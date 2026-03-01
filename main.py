"""Project Okavango — Streamlit application.

This module builds the interactive Streamlit dashboard for
environmental data analysis.  It imports the ``OwidData`` class from
``app.data`` and uses its helper methods to populate maps, charts,
KPIs, and detail panels.

Run with::

    streamlit run main.py
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from app.data import OwidData


# ------------------------------------------------------------------ #
#  Data loading (cached so it only runs once per session)             #
# ------------------------------------------------------------------ #

@st.cache_resource
def load_data() -> OwidData:
    """Instantiate and cache the data manager."""
    return OwidData()


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
            gdf["REGION_UN"].dropna().unique().tolist()
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
    sel_key = f"sel::{selected_key}::{selected_year}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = None

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
    )
    map_fig.update_layout(
        height=520,
        margin=dict(l=0, r=0, t=45, b=0),
    )

    map_event = st.plotly_chart(
        map_fig,
        on_select="rerun",
        selection_mode="points",
        key=f"map_{selected_key}_{selected_year}",
        width="stretch",
    )

    # Handle map click → select country
    if (
        map_event
        and "selection" in map_event
        and map_event["selection"]["points"]
    ):
        point = map_event["selection"]["points"][0]
        if "customdata" in point and point["customdata"]:
            st.session_state[sel_key] = str(point["customdata"][0])

    # ── KPI row ───────────────────────────────────────────────────── #
    st.subheader("Key indicators")
    valid_values = gdf[val_col].dropna()
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        st.metric("Countries with data", len(valid_values))
    with kpi2:
        st.metric(
            "Global mean",
            f"{valid_values.mean():.2f}" if len(valid_values) else "N/A",
        )
    with kpi3:
        if len(valid_values):
            idx_max = valid_values.idxmax()
            st.metric(
                "Highest",
                f"{valid_values.max():.2f}",
                delta=str(gdf.loc[idx_max, "entity"]),
            )
        else:
            st.metric("Highest", "N/A")
    with kpi4:
        if len(valid_values):
            idx_min = valid_values.idxmin()
            st.metric(
                "Lowest",
                f"{valid_values.min():.2f}",
                delta=str(gdf.loc[idx_min, "entity"]),
            )
        else:
            st.metric("Lowest", "N/A")

    # ── Comparative bar chart (top 5 / bottom 5) ─────────────────── #
    st.subheader("Top & bottom countries")
    chart_data = data.top_bottom_countries(selected_key, selected_year)

    if not chart_data.empty:
        bar_fig = px.bar(
            chart_data,
            x="entity",
            y=val_col,
            color="group",
            custom_data=["code"],
            title=f"Top and bottom 5 countries — {label}",
            color_discrete_map={
                "Top 5": "#4ade80",
                "Bottom 5": "#f87171",
            },
        )
        bar_fig.update_layout(
            height=360,
            margin=dict(l=0, r=0, t=45, b=0),
            xaxis_title="Country",
            yaxis_title=label,
        )

        bar_event = st.plotly_chart(
            bar_fig,
            on_select="rerun",
            selection_mode="points",
            key=f"bar_{selected_key}_{selected_year}",
            width="stretch",
        )

        # Handle bar click → select country
        if (
            bar_event
            and "selection" in bar_event
            and bar_event["selection"]["points"]
        ):
            point = bar_event["selection"]["points"][0]
            if "customdata" in point and point["customdata"]:
                st.session_state[sel_key] = str(point["customdata"][0])
                st.rerun()
    else:
        st.info("No country data available for this year.")

    # ── Country detail panel + trend line ─────────────────────────── #
    selected_code: str | None = st.session_state[sel_key]
    details_col, trend_col = st.columns([1, 2], gap="large")

    with details_col:
        st.subheader("Selection details")
        if selected_code is None:
            st.info("Click a country on the map or bar chart.")
        else:
            details = data.country_details(
                selected_key, selected_code, selected_year,
            )
            if details is None:
                st.warning(
                    "No data for this country in the selected "
                    "dataset / year."
                )
            else:
                st.metric("Country", details["entity"])
                st.metric("Region", details["region"])
                st.metric("Value", f"{details['value']:.2f}")
                st.metric("Rank", f"#{details['rank']}")
                delta = details["delta"]
                st.metric(
                    "Change vs. previous year",
                    "N/A" if delta is None else f"{delta:+.2f}",
                )

    with trend_col:
        st.subheader("Trend")
        if selected_code is None:
            st.info("Trend appears after selecting a country.")
        else:
            trend = data.country_timeseries(selected_key, selected_code)
            if trend.empty:
                st.warning("No time-series data for this country.")
            else:
                trend_fig = px.line(
                    trend,
                    x="year",
                    y=val_col,
                    markers=True,
                    title=(
                        f"{trend['entity'].iloc[0]} · {label}"
                    ),
                )
                trend_fig.update_layout(
                    height=320,
                    margin=dict(l=0, r=0, t=45, b=0),
                )
                st.plotly_chart(trend_fig, width="stretch")


if __name__ == "__main__":
    main()