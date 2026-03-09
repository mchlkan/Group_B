"""AI pipeline stub — interface for backend teammates.

This module defines the function signatures that the Satellite Analysis
page calls.  Each function currently returns placeholder data so the UI
can render.  Teammates will replace the bodies with real implementations
(Ollama calls, satellite tile downloads, database lookups, etc.).
"""

from __future__ import annotations

import base64
import io
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image
import yaml

ESRI_EXPORT_URL = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/export"
)
"""ArcGIS REST endpoint used to export imagery for a bounding box."""

ESRI_TILE_URL = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile"
)
"""ArcGIS REST endpoint used to fetch XYZ image tiles."""

ESRI_TILE_URL_ALT = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile"
)
"""Alternate ArcGIS tile host used as a network fallback."""

IMAGE_DIR = Path("images")
"""Directory where downloaded satellite images are stored."""

IMAGE_SIZE_PX = 1024
"""Square image size used for exported satellite snapshots."""

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
"""Base URL for the local Ollama HTTP server."""

MODELS_CONFIG_PATH = Path("models.yaml")
"""Repository-level YAML config for AI model and prompt settings."""

DEFAULT_IMAGE_MODEL = "qwen2.5vl:3b"
"""Default lightweight multimodal model used for image description."""

DEFAULT_IMAGE_PROMPT = (
    "Describe this satellite image in 4-6 concise sentences. "
    "Focus on land cover, visible human activity, vegetation, water, and any "
    "obvious signs of deforestation, drought, fire scars, flooding, erosion, "
    "or pollution."
)
"""Default prompt used for image-to-text description."""

DEFAULT_IMAGE_OPTIONS: dict[str, Any] = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_predict": 80,
}
"""Default Ollama generation options for image description."""


def _is_valid_input(latitude: float, longitude: float, zoom: int) -> bool:
    """Return ``True`` when latitude/longitude/zoom are within bounds."""
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0 and 1 <= zoom <= 18


def _tile_xy_from_latlon(latitude: float, longitude: float, zoom: int) -> tuple[int, int]:
    """Convert geographic coordinates to integer Slippy Map tile indices.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees.
    longitude : float
        Longitude in decimal degrees.
    zoom : int
        Slippy Map zoom level.

    Returns
    -------
    tuple[int, int]
        Tile indices ``(x, y)`` for the supplied coordinate.

    """
    lat_clamped = max(-85.05112878, min(85.05112878, latitude))
    n_tiles = 2**zoom
    x_float = (longitude + 180.0) / 360.0 * n_tiles
    lat_rad = math.radians(lat_clamped)
    y_float = (
        1.0
        - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi
    ) / 2.0 * n_tiles

    x_tile = min(n_tiles - 1, max(0, int(x_float)))
    y_tile = min(n_tiles - 1, max(0, int(y_float)))
    return x_tile, y_tile


def _lon_from_tile_x(tile_x: int, zoom: int) -> float:
    """Convert tile x index to longitude at the tile boundary."""
    return tile_x / (2**zoom) * 360.0 - 180.0


def _lat_from_tile_y(tile_y: int, zoom: int) -> float:
    """Convert tile y index to latitude at the tile boundary."""
    n = math.pi - (2.0 * math.pi * tile_y) / (2**zoom)
    return math.degrees(math.atan(math.sinh(n)))


def _bbox_for_coordinate(latitude: float, longitude: float, zoom: int) -> tuple[float, float, float, float]:
    """Build a WGS84 bounding box for the tile containing the coordinate.

    Returns
    -------
    tuple[float, float, float, float]
        Bounding box as ``(xmin, ymin, xmax, ymax)`` in EPSG:4326.

    """
    x_tile, y_tile = _tile_xy_from_latlon(latitude, longitude, zoom)

    west = _lon_from_tile_x(x_tile, zoom)
    east = _lon_from_tile_x(x_tile + 1, zoom)
    north = _lat_from_tile_y(y_tile, zoom)
    south = _lat_from_tile_y(y_tile + 1, zoom)
    return west, south, east, north


def _image_filename(latitude: float, longitude: float, zoom: int) -> Path:
    """Return deterministic image path for a coordinate request."""
    filename = f"esri_{latitude:.4f}_{longitude:.4f}_z{zoom}.jpg"
    return IMAGE_DIR / filename


def _download_to_path(
    url: str,
    output_path: Path,
    timeout: int = 35,
    attempts: int = 2,
) -> bool:
    """Download binary content from *url* and store it at *output_path*.

    Retries a small number of times to handle transient network errors in
    hosted environments.
    """
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                image_bytes = response.read()
            if not image_bytes:
                raise ValueError("Empty response body.")
            output_path.write_bytes(image_bytes)
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            # Keep logs concise but visible in Streamlit Cloud runtime logs.
            print(
                f"[fetch_satellite_image] attempt={attempt}/{attempts} "
                f"failed url={url} error={type(exc).__name__}: {exc}",
            )

    return False


def _ollama_request(
    endpoint: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any] | None:
    """Send an HTTP request to Ollama and return parsed JSON data."""
    url = f"{OLLAMA_BASE_URL}{endpoint}"
    method = "GET" if payload is None else "POST"
    data = None
    headers = {"Content-Type": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8").strip()
    except Exception:
        return None

    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _load_models_config() -> dict[str, Any]:
    """Load AI workflow configuration from ``models.yaml``.

    Returns
    -------
    dict[str, Any]
        Parsed configuration dictionary. Returns an empty dictionary when
        the file is missing or invalid.

    """
    if not MODELS_CONFIG_PATH.exists():
        return {}

    try:
        loaded = yaml.safe_load(MODELS_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _image_description_config() -> tuple[str, str, dict[str, Any]]:
    """Return image description model settings from YAML with safe defaults."""
    config = _load_models_config()
    section = config.get("image_description", {})
    if not isinstance(section, dict):
        section = {}

    model = str(section.get("model", DEFAULT_IMAGE_MODEL)).strip() or DEFAULT_IMAGE_MODEL
    prompt = str(section.get("prompt", DEFAULT_IMAGE_PROMPT)).strip() or DEFAULT_IMAGE_PROMPT

    options = section.get("options", DEFAULT_IMAGE_OPTIONS)
    if not isinstance(options, dict):
        options = DEFAULT_IMAGE_OPTIONS

    return model, prompt, options


def _encode_image_for_ollama(image_file: Path, max_size: int = 448) -> str:
    """Return a base64 JPEG string optimized for faster multimodal inference.

    The image is converted to RGB and downscaled (while preserving aspect ratio)
    to reduce vision token cost and request size.
    """
    with Image.open(image_file) as img:
        rgb_img = img.convert("RGB")
        rgb_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        rgb_img.save(buffer, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _ollama_has_model(model_name: str) -> bool:
    """Return ``True`` if Ollama already has *model_name* available locally."""
    tags = _ollama_request("/api/tags")
    if not tags:
        return False

    models = tags.get("models", [])
    target = model_name.strip()
    target_base = target.split(":", maxsplit=1)[0]

    for model in models:
        local_name = str(model.get("name", "")).strip()
        local_base = local_name.split(":", maxsplit=1)[0]
        if local_name == target or local_base == target_base:
            return True
    return False


def _ensure_ollama_model(model_name: str) -> bool:
    """Ensure Ollama has *model_name*; pulls it when missing."""
    if _ollama_has_model(model_name):
        return True

    pull_payload = {
        "name": model_name,
        "stream": False,
    }
    pulled = _ollama_request(
        "/api/pull",
        payload=pull_payload,
        timeout=600,
    )
    if pulled is None:
        return False

    return _ollama_has_model(model_name)


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
    if not _is_valid_input(latitude, longitude, zoom):
        return None

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _image_filename(latitude, longitude, zoom)

    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)

    bbox = _bbox_for_coordinate(latitude, longitude, zoom)
    bbox_value = ",".join(f"{value:.8f}" for value in bbox)

    query_params = {
        "bbox": bbox_value,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{IMAGE_SIZE_PX},{IMAGE_SIZE_PX}",
        "format": "jpg",
        "transparent": "false",
        "f": "image",
    }
    query = urllib.parse.urlencode(query_params)
    request_url = f"{ESRI_EXPORT_URL}?{query}"
    if _download_to_path(request_url, output_path):
        return str(output_path)

    # Fallback for high zoom requests where export may fail on tiny bbox.
    x_tile, y_tile = _tile_xy_from_latlon(latitude, longitude, zoom)
    tile_url = f"{ESRI_TILE_URL}/{zoom}/{y_tile}/{x_tile}"
    if _download_to_path(tile_url, output_path):
        return str(output_path)

    alt_tile_url = f"{ESRI_TILE_URL_ALT}/{zoom}/{y_tile}/{x_tile}"
    if _download_to_path(alt_tile_url, output_path):
        return str(output_path)

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
    image_file = Path(image_path)
    if not image_file.exists() or image_file.stat().st_size == 0:
        return {
            "description": "Image file not found or empty.",
            "danger_level": 0,
            "danger_label": "Unknown",
        }

    model_name, prompt, options = _image_description_config()

    if not _ensure_ollama_model(model_name):
        return {
            "description": (
                "Could not access Ollama model for image description. "
                "Check that Ollama is installed and running."
            ),
            "danger_level": 0,
            "danger_label": "Unknown",
        }

    image_b64 = _encode_image_for_ollama(image_file)
    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [image_b64],
        "options": options,
        "think": False,
        "stream": False,
    }

    result = _ollama_request(
        "/api/generate",
        payload=payload,
        timeout=300,
    )
    if result is None:
        return {
            "description": (
                "Ollama did not return a response in time. "
                "Try reducing num_predict in models.yaml or use a smaller model."
            ),
            "danger_level": 0,
            "danger_label": "Unknown",
        }

    description = str(result.get("response", "")).strip()
    if not description:
        description = "No description generated by the model."

    return {
        "description": description,
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
