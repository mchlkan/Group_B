"""Project Okavango — Satellite Analysis page.

Provides a UI for analysing satellite imagery at user-specified
coordinates.  Backend functions (image download, AI analysis, database)
are imported from ``app.ai_pipeline`` and are currently stubs that
teammates will implement.
"""

from __future__ import annotations

import streamlit as st

from app.ai_pipeline import (
    analyze_image,
    fetch_satellite_image,
    load_previous_analysis,
    save_analysis,
)

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

    # ── Sidebar inputs ────────────────────────────────────────────── #
    with st.sidebar:
        st.header("Coordinates")

        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=0.0,
            step=0.01,
            format="%.4f",
        )
        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=0.0,
            step=0.01,
            format="%.4f",
        )
        zoom = st.slider("Zoom level", min_value=1, max_value=18, value=10)

        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    # ── Main area ─────────────────────────────────────────────────── #

    if analyze_btn:
        with st.spinner("Fetching satellite image..."):
            image_path = fetch_satellite_image(latitude, longitude, zoom)

        if image_path is None:
            st.warning(
                "Could not fetch satellite image. "
                "The image download backend is not yet connected."
            )
            # Show placeholder layout even without a real image
            _render_placeholder(latitude, longitude, zoom)
            return

        with st.spinner("Running AI analysis..."):
            analysis = analyze_image(image_path)

        # Persist result (best-effort; stub returns False)
        save_analysis(latitude, longitude, zoom, image_path, analysis)

        # Store in session so it survives reruns
        st.session_state["sat_result"] = {
            "image_path": image_path,
            "analysis": analysis,
            "latitude": latitude,
            "longitude": longitude,
            "zoom": zoom,
        }

    # Render stored result if available
    result = st.session_state.get("sat_result")
    if result:
        _render_result(result)
    elif not analyze_btn:
        st.info("Enter coordinates in the sidebar and press **Analyze** to begin.")


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


page()
