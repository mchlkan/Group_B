"""Project Okavango — Satellite Analysis page.

Provides a UI for analysing satellite imagery at user-specified
coordinates.  Backend functions (image download, AI analysis, database)
are imported from ``app.ai_pipeline`` and are currently stubs that
teammates will implement.
"""

from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from app.ai_pipeline import (OllamaUnavailableError, analyze_image,
                             fetch_satellite_image,
                             get_image_model_display_name,
                             get_image_model_name, get_risk_model_display_name,
                             get_risk_model_name, load_previous_analysis,
                             ollama_has_model, pull_model_stream,
                             save_analysis)

# ------------------------------------------------------------------ #
#  Danger-level colour mapping                                         #
# ------------------------------------------------------------------ #

_DANGER_COLORS: dict[int, str] = {
    0: "#9ca3af",  # grey   — Unknown
    1: "#22c55e",  # green  — Very Low
    2: "#84cc16",  # lime   — Low
    3: "#eab308",  # yellow — Moderate
    4: "#f97316",  # orange — High
    5: "#ef4444",  # red    — Critical
}


def _download_model(model_name: str, display_name: str) -> bool:
    """Download an Ollama model with a progress UI. Returns True on success."""
    info_slot = st.empty()
    info_slot.info(f"Model **{display_name}** not found locally — downloading…")
    status_slot = st.empty()
    progress_slot = st.empty()
    progress_slot.progress(0.0, text="Starting download…")

    for event in pull_model_stream(model_name):
        status_text = event.get("status", "")
        total = event.get("total", 0)
        completed = event.get("completed", 0)

        if status_text.startswith("error:"):
            info_slot.empty()
            status_slot.empty()
            progress_slot.empty()
            st.error(f"Download failed: {status_text}")
            return False

        if total:
            fraction = min(completed / total, 1.0)
            mb_done = completed / 1_048_576
            mb_total = total / 1_048_576
            progress_slot.progress(
                fraction,
                text=f"Downloading {display_name} — {mb_done:.0f} MB / {mb_total:.0f} MB",
            )
        else:
            status_slot.text(f"⏳ {display_name}: {status_text}")

        if status_text == "success":
            info_slot.empty()
            status_slot.empty()
            progress_slot.empty()
            return True

    return False


def _danger_badge(level: int, label: str) -> str:
    """Return an HTML badge for the danger level."""
    color = _DANGER_COLORS.get(level, _DANGER_COLORS[0])
    return (
        f'<span style="background:{color};color:#fff;padding:4px 12px;'
        f'border-radius:8px;font-weight:600;font-size:1.1rem;">'
        f"{label} ({level}/5)</span>"
    )


# ------------------------------------------------------------------ #
#  Page entry point                                                    #
# ------------------------------------------------------------------ #


def page() -> None:
    """Render the Satellite Analysis page."""
    st.title("Satellite Analysis")
    st.caption("Analyse satellite imagery with AI-powered risk assessment")

    # Initialise session state for coordinates
    if "sat_lat" not in st.session_state:
        st.session_state["sat_lat"] = 38.6780
    if "sat_lon" not in st.session_state:
        st.session_state["sat_lon"] = -9.3222

    # ── Sidebar inputs ────────────────────────────────────────────── #
    with st.sidebar:
        st.header("Coordinates")

        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=st.session_state["sat_lat"],
            step=0.01,
            format="%.4f",
            help="Range: -90 (South Pole) to 90 (North Pole)",
        )
        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=st.session_state["sat_lon"],
            step=0.01,
            format="%.4f",
            help="Range: -180 (West) to 180 (East)",
        )
        zoom = st.slider(
            "Zoom level",
            min_value=1,
            max_value=18,
            value=10,
            help="1 = whole world, 18 = street level. Standard range for web map tile servers (OSM, Google, Mapbox).",
        )

        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    # ── Clickable map for coordinate selection ────────────────────── #
    st.subheader("Select location")
    st.caption("Click on the map to set coordinates, or enter them in the sidebar.")

    m = folium.Map(location=[latitude, longitude], zoom_start=zoom)
    folium.CircleMarker(
        [latitude, longitude],
        radius=8,
        color="#e74c3c",
        fill=True,
        fill_color="#e74c3c",
        fill_opacity=0.9,
        tooltip=f"{latitude:.4f}, {longitude:.4f}",
    ).add_to(m)

    map_data = st_folium(m, height=400, width=None, key="coord_map")

    # Update coordinates when the user clicks the map
    if map_data and map_data.get("last_clicked"):
        clicked_lat = map_data["last_clicked"]["lat"]
        clicked_lon = map_data["last_clicked"]["lng"]
        clamped_lat = max(-90.0, min(90.0, round(clicked_lat, 4)))
        clamped_lon = max(-180.0, min(180.0, round(clicked_lon, 4)))
        if clamped_lat != st.session_state["sat_lat"] or clamped_lon != st.session_state["sat_lon"]:
            st.session_state["sat_lat"] = clamped_lat
            st.session_state["sat_lon"] = clamped_lon
            st.rerun()

    st.divider()

    # ── Analysis area ─────────────────────────────────────────────── #

    if analyze_btn:
        with st.spinner("Fetching satellite image..."):
            image_path = fetch_satellite_image(latitude, longitude, zoom)

        if image_path is None:
            st.warning(
                "Could not fetch satellite image. "
                "The image download backend is not yet connected."
            )
            _render_placeholder(latitude, longitude, zoom)
            return

        # ── Model download (only when not already present) ──────── #
        try:
            model_name = get_image_model_name()
            model_ready = ollama_has_model(model_name)

            if not model_ready:
                display_name = get_image_model_display_name()
                if not _download_model(model_name, display_name):
                    return

            # ── Risk classification model download ────────────────────── #
            risk_model_name = get_risk_model_name()
            risk_model_ready = ollama_has_model(risk_model_name)

            if not risk_model_ready:
                risk_display_name = get_risk_model_display_name()
                if not _download_model(risk_model_name, risk_display_name):
                    return

            analysis_info = st.empty()
            analysis_info.info("Running AI analysis on this image…")

            with st.spinner("Running AI analysis..."):
                analysis = analyze_image(image_path)

            analysis_info.empty()

            save_analysis(latitude, longitude, zoom, image_path, analysis)

            st.session_state["sat_result"] = {
                "image_path": image_path,
                "analysis": analysis,
                "latitude": latitude,
                "longitude": longitude,
                "zoom": zoom,
            }
        except OllamaUnavailableError as exc:
            st.error(
                f"**Ollama is not running.**\n\n{exc}\n\n"
                "Please start Ollama (`ollama serve`) and try again."
            )
            return

    result = st.session_state.get("sat_result")
    if result:
        _render_result(result)
    elif not analyze_btn:
        st.info("Enter coordinates in the sidebar (or click the map) and press **Analyze** to begin.")


def _render_placeholder(lat: float, lon: float, zoom: int) -> None:
    """Show the layout with placeholder content when no image is available."""
    img_col, desc_col = st.columns(2)

    with img_col:
        st.subheader("Satellite Image")
        st.info(
            f"Image placeholder for ({lat:.4f}, {lon:.4f}) at zoom {zoom}.\n\n"
            "Connect `fetch_satellite_image()` in `app/ai_pipeline.py` to display real imagery."
        )

    with desc_col:
        st.subheader("Image Description")
        st.info("AI description will appear here once the backend is connected.")

    st.divider()
    st.subheader("Risk Assessment")
    st.markdown(
        _danger_badge(0, "Unknown"),
        unsafe_allow_html=True,
    )
    st.info("Risk assessment will appear here once the AI pipeline is connected.")


def _render_result(result: dict) -> None:
    """Display the satellite image, description, and risk assessment."""
    analysis = result["analysis"]
    image_path = result["image_path"]

    img_col, desc_col = st.columns(2)

    with img_col:
        st.subheader("Satellite Image")
        st.image(image_path, use_container_width=True)
        st.caption(
            f"({result['latitude']:.4f}, {result['longitude']:.4f}) "
            f"· zoom {result['zoom']}"
        )

    with desc_col:
        st.subheader("Image Description")
        st.write(analysis.get("description", "No description available."))

    st.divider()
    st.subheader("Risk Assessment")
    level = analysis.get("danger_level", 0)
    label = analysis.get("danger_label", "Unknown")
    st.markdown(_danger_badge(level, label), unsafe_allow_html=True)

    danger_reason = analysis.get("danger_reason", "")
    if danger_reason:
        st.markdown(f"**Reason:** {danger_reason}")


page()
