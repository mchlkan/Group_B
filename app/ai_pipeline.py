"""AI pipeline — satellite image retrieval and AI-powered risk analysis.

This module implements the full AI analysis workflow for Project Okavango:
satellite tile downloading from ArcGIS, image description via a local
Ollama multimodal model, and environmental risk classification.  Model
and prompt settings are configurable through ``models.yaml``.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

import yaml
from PIL import Image

logger = logging.getLogger(__name__)

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


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server cannot be reached."""


MODELS_CONFIG_PATH = Path("models.yaml")
"""Repository-level YAML config for AI model and prompt settings."""

DEFAULT_IMAGE_MODEL = "qwen3.5:2b"
"""Default lightweight multimodal model used for image description."""

DEFAULT_IMAGE_PROMPT = (
    "Describe this satellite image in 4-6 concise sentences. "
    "Focus on land cover, vegetation health and coverage, water "
    "bodies, and any signs of environmental degradation such as "
    "deforestation, drought, fire scars, flooding, erosion, "
    "pollution, or bare/degraded soil. Note whether vegetation "
    "appears healthy or stressed, and whether natural areas appear "
    "intact or damaged."
)
"""Default prompt used for image-to-text description."""

DEFAULT_IMAGE_OPTIONS: dict[str, Any] = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_predict": 80,
}
"""Default Ollama generation options for image description."""

DEFAULT_RISK_MODEL = "qwen3.5:4b"
"""Default text model used for environmental risk classification."""

DEFAULT_RISK_PROMPT = (
    "You are an environmental risk analyst. Given the following satellite "
    "image description, classify the environmental danger level.\n"
    "Focus ONLY on environmental DEGRADATION: deforestation, drought, "
    "fire scars, flooding, erosion, pollution, and land degradation. "
    "IMPORTANT: Natural landscapes are NOT dangerous even if they look "
    "sparse. Savanna, scrubland, steppe, arid woodland, and other "
    "naturally sparse biomes with scattered trees and bare soil between "
    "them are HEALTHY ecosystems — rate them 1 or 2. Cities and towns "
    "with green space are also low risk. Only rate 3+ when you see "
    "ACTUAL DAMAGE like clear-cut areas, burn marks, polluted water, "
    "or eroded hillsides.\n\n"
    "Scoring criteria:\n"
    "1 (Very Low): Natural landscape — forest, savanna, grassland, scrubland, or any area with no visible damage.\n"
    "2 (Low): Mostly natural with minor human presence (roads, small farms) but no visible environmental damage.\n"
    "3 (Moderate): Visible signs of environmental stress — patches of cleared forest, early erosion, or degraded vegetation that looks unnatural.\n"
    "4 (High): Clear environmental damage — active deforestation, visible pollution, significant erosion, or drought-stressed/dying vegetation.\n"
    "5 (Critical): Severe destruction — large-scale deforestation, heavy pollution, fire scars, barren degraded land, or severe flooding.\n\n"
    "You MUST respond in EXACTLY this format (three lines, nothing else):\n\n"
    "Level: <number from 1 to 5>\n"
    "Label: <one of: Very Low, Low, Moderate, High, Critical>\n"
    "Reason: <one sentence explaining the risk>\n\n"
    "Image description:\n"
)
"""Default prompt used for risk classification."""

DEFAULT_RISK_OPTIONS: dict[str, Any] = {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_predict": 120,
}
"""Default Ollama generation options for risk classification."""


def _is_valid_input(latitude: float, longitude: float, zoom: int) -> bool:
    """Return ``True`` when latitude/longitude/zoom are within bounds."""
    return (
        -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0 and 1 <= zoom <= 18
    )


def _tile_xy_from_latlon(
    latitude: float, longitude: float, zoom: int
) -> tuple[int, int]:
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
        (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)
        / 2.0
        * n_tiles
    )

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


def _bbox_for_coordinate(
    latitude: float, longitude: float, zoom: int
) -> tuple[float, float, float, float]:
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
            return True
        except (OSError, ValueError) as exc:
            logger.warning(
                "[fetch_satellite_image] attempt=%d/%d failed url=%s error=%s: %s",
                attempt,
                attempts,
                url,
                type(exc).__name__,
                exc,
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
    except OSError as exc:
        raise OllamaUnavailableError(
            f"Ollama is not reachable at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is installed and running."
        ) from exc

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
    except (OSError, yaml.YAMLError):
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _image_description_config() -> tuple[str, str, dict[str, Any]]:
    """Return image description model settings from YAML with safe defaults."""
    config = _load_models_config()
    section = config.get("image_description", {})
    if not isinstance(section, dict):
        section = {}

    model = (
        str(section.get("model", DEFAULT_IMAGE_MODEL)).strip() or DEFAULT_IMAGE_MODEL
    )
    prompt = (
        str(section.get("prompt", DEFAULT_IMAGE_PROMPT)).strip() or DEFAULT_IMAGE_PROMPT
    )

    options = section.get("options", DEFAULT_IMAGE_OPTIONS)
    if not isinstance(options, dict):
        options = DEFAULT_IMAGE_OPTIONS

    return model, prompt, options


def _risk_classification_config() -> tuple[str, str, dict[str, Any]]:
    """Return risk classification model settings from YAML with safe defaults."""
    config = _load_models_config()
    section = config.get("risk_classification", {})
    if not isinstance(section, dict):
        section = {}

    model = str(section.get("model", DEFAULT_RISK_MODEL)).strip() or DEFAULT_RISK_MODEL
    prompt = (
        str(section.get("prompt", DEFAULT_RISK_PROMPT)).strip() or DEFAULT_RISK_PROMPT
    )

    options = section.get("options", DEFAULT_RISK_OPTIONS)
    if not isinstance(options, dict):
        options = DEFAULT_RISK_OPTIONS

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

    for model in models:
        local_name = str(model.get("name", "")).strip()
        if local_name == target:
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
    _ollama_request(
        "/api/pull",
        payload=pull_payload,
        timeout=600,
    )

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


def _parse_risk_response(text: str) -> tuple[int, str, str]:
    """Extract (level, label, reason) from a structured risk response.

    Falls back to ``(0, "Unknown", "")`` when the response cannot be parsed.
    """
    level = 0
    label = "Unknown"
    reason = ""

    level_match = re.search(r"Level\s*:\s*(\d)", text, re.IGNORECASE)
    if level_match:
        parsed = int(level_match.group(1))
        if 1 <= parsed <= 5:
            level = parsed

    label_match = re.search(
        r"Label\s*:\s*(Very Low|Low|Moderate|High|Critical)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        label = label_match.group(1).title()

    reason_match = re.search(r"Reason\s*:\s*(.+)", text, re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()

    return level, label, reason


def classify_risk(description: str) -> dict:
    """Classify environmental risk from a satellite image description.

    Parameters
    ----------
    description : str
        Natural-language description of the satellite image.

    Returns
    -------
    dict
        Classification result with keys ``danger_level``, ``danger_label``,
        ``danger_reason``, ``text_description``, ``text_model``, and
        ``text_prompt``.
    """
    model_name, prompt_template, options = _risk_classification_config()
    full_prompt = f"{prompt_template}\n{description}"

    fallback: dict[str, Any] = {
        "danger_level": 0,
        "danger_label": "Unknown",
        "danger_reason": "",
        "text_description": "",
        "text_model": model_name,
        "text_prompt": full_prompt,
    }

    if not _ensure_ollama_model(model_name):
        return fallback

    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "options": options,
        "think": False,
        "stream": False,
    }

    result = _ollama_request("/api/generate", payload=payload, timeout=120)
    if result is None:
        logger.warning("[classify_risk] Ollama returned None for model=%s", model_name)
        return fallback

    raw_response = str(result.get("response", "")).strip()
    # Strip <think>...</think> blocks in case thinking mode leaked through
    raw_response = re.sub(
        r"<think>.*?</think>", "", raw_response, flags=re.DOTALL
    ).strip()
    if not raw_response:
        logger.warning("[classify_risk] Empty response from model")
        return fallback

    logger.debug("[classify_risk] Raw response: %r", raw_response)
    level, label, reason = _parse_risk_response(raw_response)

    return {
        "danger_level": level,
        "danger_label": label,
        "danger_reason": reason,
        "text_description": raw_response,
        "text_model": model_name,
        "text_prompt": full_prompt,
    }


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

    risk = classify_risk(description)

    return {
        "description": description,
        "image_model": model_name,
        "image_prompt": prompt,
        "danger_level": risk["danger_level"],
        "danger_label": risk["danger_label"],
        "danger_reason": risk["danger_reason"],
        "text_description": risk["text_description"],
        "text_model": risk["text_model"],
        "text_prompt": risk["text_prompt"],
    }


def get_image_model_name() -> str:
    """Return the configured image-description model name."""
    model, _, _ = _image_description_config()
    return model


def get_image_model_display_name() -> str:
    """Return the human-friendly display name for the image model."""
    config = _load_models_config()
    section = config.get("image_description", {})
    if isinstance(section, dict) and section.get("display_name"):
        return str(section["display_name"]).strip()
    return get_image_model_name()


def get_risk_model_name() -> str:
    """Return the configured risk-classification model name."""
    model, _, _ = _risk_classification_config()
    return model


def get_risk_model_display_name() -> str:
    """Return the human-friendly display name for the risk model."""
    config = _load_models_config()
    section = config.get("risk_classification", {})
    if isinstance(section, dict) and section.get("display_name"):
        return str(section["display_name"]).strip()
    return get_risk_model_name()


def ollama_has_model(model_name: str) -> bool:
    """Return ``True`` if Ollama has *model_name* available locally."""
    return _ollama_has_model(model_name)


def pull_model_stream(model_name: str) -> Iterator[dict]:
    """Stream pull-progress events from Ollama for *model_name*.

    Yields one ``dict`` per progress line reported by Ollama.  Each dict
    contains at least a ``"status"`` key and optionally ``"total"`` and
    ``"completed"`` (bytes) when a layer is being downloaded.

    Yields ``{"status": "error: <msg>"}`` and stops on any failure.
    """
    url = f"{OLLAMA_BASE_URL}/api/pull"
    payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield event
                if event.get("status") == "success":
                    return
    except Exception as exc:
        yield {"status": f"error: {type(exc).__name__}: {exc}"}


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
    from app.database import insert_analysis

    return insert_analysis(latitude, longitude, zoom, image_path, analysis)


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
    from app.database import lookup_analysis

    return lookup_analysis(latitude, longitude, zoom)
