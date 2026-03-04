"""AI pipeline stub — interface for backend teammates.

This module defines the function signatures that the Satellite Analysis
page calls.  Each function currently returns placeholder data so the UI
can render.  Teammates will replace the bodies with real implementations
(Ollama calls, satellite tile downloads, database lookups, etc.).
"""

from __future__ import annotations


def fetch_satellite_image(
    latitude: float,
    longitude: float,
    zoom: int,
) -> str | None:
    """Download a satellite image tile and return its local file path.

    Parameters
    ----------
    latitude : float
        Latitude of the centre point (-90 to 90).
    longitude : float
        Longitude of the centre point (-180 to 180).
    zoom : int
        Map zoom level (1–18).

    Returns
    -------
    str or None
        Local file path to the downloaded image, or ``None`` on failure.

    """
    # TODO: implement satellite tile download (e.g. Google Static Maps,
    #       Mapbox, or OpenStreetMap tile server).
    return None


def analyze_image(image_path: str) -> dict:
    """Send a satellite image to the AI model for analysis.

    Parameters
    ----------
    image_path : str
        Path to the satellite image file on disk.

    Returns
    -------
    dict
        Analysis result with keys:
        - ``"description"`` (str): natural-language description of the image
        - ``"danger_level"`` (int): risk score from 1 (low) to 5 (critical)
        - ``"danger_label"`` (str): human-readable label, e.g. "Moderate"

    """
    # TODO: implement Ollama / LLM call with the image.
    return {
        "description": "Placeholder — AI analysis not yet connected.",
        "danger_level": 0,
        "danger_label": "Unknown",
    }


def save_analysis(
    latitude: float,
    longitude: float,
    zoom: int,
    image_path: str,
    analysis: dict,
) -> bool:
    """Persist an analysis result to the database.

    Parameters
    ----------
    latitude, longitude : float
        Coordinates that were analysed.
    zoom : int
        Zoom level used.
    image_path : str
        Path to the satellite image.
    analysis : dict
        The dict returned by :func:`analyze_image`.

    Returns
    -------
    bool
        ``True`` if the record was saved successfully.

    """
    # TODO: implement database insert (SQLite / PostgreSQL / etc.).
    return False


def load_previous_analysis(
    latitude: float,
    longitude: float,
    zoom: int,
) -> dict | None:
    """Look up a previously saved analysis for the given coordinates.

    Parameters
    ----------
    latitude, longitude : float
        Coordinates to search for.
    zoom : int
        Zoom level used.

    Returns
    -------
    dict or None
        Previously saved analysis dict, or ``None`` if not found.

    """
    # TODO: implement database lookup.
    return None
