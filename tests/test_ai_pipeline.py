"""Unit tests for app.ai_pipeline — covers pure functions, Pydantic, and mocked API."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.ai_pipeline import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_OPTIONS,
    DEFAULT_IMAGE_PROMPT,
    DEFAULT_RISK_MODEL,
    DEFAULT_RISK_OPTIONS,
    DEFAULT_RISK_PROMPT,
    IMAGE_DIR,
    AnalysisResult,
    ModelsConfig,
    OllamaUnavailableError,
    RiskResult,
    _bbox_for_coordinate,
    _download_to_path,
    _encode_image_for_ollama,
    _ensure_ollama_model,
    _image_description_config,
    _image_filename,
    _is_valid_input,
    _load_models_config,
    _ollama_has_model,
    _ollama_request,
    _parse_risk_response,
    _risk_classification_config,
    _tile_xy_from_latlon,
    analyze_image,
    classify_risk,
    fetch_satellite_image,
    get_image_model_display_name,
    get_image_model_name,
    get_risk_model_display_name,
    get_risk_model_name,
    load_previous_analysis,
    ollama_has_model,
    pull_model_stream,
    save_analysis,
)

# ── _is_valid_input ────────────────────────────────────────────────── #


class TestIsValidInput:
    def test_valid_coords(self):
        assert _is_valid_input(0.0, 0.0, 10) is True

    def test_boundary_lat(self):
        assert _is_valid_input(90.0, 0.0, 1) is True
        assert _is_valid_input(-90.0, 0.0, 1) is True

    def test_boundary_lon(self):
        assert _is_valid_input(0.0, 180.0, 1) is True
        assert _is_valid_input(0.0, -180.0, 1) is True

    def test_boundary_zoom(self):
        assert _is_valid_input(0.0, 0.0, 1) is True
        assert _is_valid_input(0.0, 0.0, 18) is True

    def test_out_of_range_lat(self):
        assert _is_valid_input(91.0, 0.0, 10) is False
        assert _is_valid_input(-91.0, 0.0, 10) is False

    def test_out_of_range_lon(self):
        assert _is_valid_input(0.0, 181.0, 10) is False
        assert _is_valid_input(0.0, -181.0, 10) is False

    def test_out_of_range_zoom(self):
        assert _is_valid_input(0.0, 0.0, 0) is False
        assert _is_valid_input(0.0, 0.0, 19) is False


# ── _tile_xy_from_latlon ──────────────────────────────────────────── #


class TestTileXYFromLatLon:
    def test_origin_zoom1(self):
        x, y = _tile_xy_from_latlon(0.0, 0.0, 1)
        assert x == 1
        assert y == 1

    def test_known_coordinate(self):
        # London (~51.5, -0.1) at zoom 10 — well-known tile indices
        x, y = _tile_xy_from_latlon(51.5, -0.1, 10)
        assert x == 511
        assert y == 340

    def test_returns_integers(self):
        x, y = _tile_xy_from_latlon(38.678, -9.322, 12)
        assert isinstance(x, int)
        assert isinstance(y, int)


# ── _bbox_for_coordinate ──────────────────────────────────────────── #


class TestBboxForCoordinate:
    def test_ordering(self):
        west, south, east, north = _bbox_for_coordinate(38.678, -9.322, 10)
        assert west < east
        assert south < north

    def test_contains_point(self):
        lat, lon = 51.5, -0.1
        west, south, east, north = _bbox_for_coordinate(lat, lon, 12)
        assert west <= lon <= east
        assert south <= lat <= north


# ── _image_filename ───────────────────────────────────────────────── #


class TestImageFilename:
    def test_deterministic(self):
        p1 = _image_filename(38.678, -9.322, 10)
        p2 = _image_filename(38.678, -9.322, 10)
        assert p1 == p2

    def test_path_under_image_dir(self):
        p = _image_filename(0.0, 0.0, 5)
        assert p.parent == IMAGE_DIR

    def test_extension(self):
        p = _image_filename(10.0, 20.0, 8)
        assert p.suffix == ".jpg"

    def test_different_coords_differ(self):
        p1 = _image_filename(10.0, 20.0, 8)
        p2 = _image_filename(11.0, 20.0, 8)
        assert p1 != p2


# ── _parse_risk_response ──────────────────────────────────────────── #


class TestParseRiskResponse:
    def test_well_formed(self):
        text = "Level: 3\nLabel: Moderate\nReason: Some deforestation visible."
        level, label, reason = _parse_risk_response(text)
        assert level == 3
        assert label == "Moderate"
        assert reason == "Some deforestation visible."

    def test_partial_only_level(self):
        level, label, reason = _parse_risk_response("Level: 4")
        assert level == 4
        assert label == "Unknown"
        assert reason == ""

    def test_garbage_input(self):
        level, label, reason = _parse_risk_response("totally irrelevant text")
        assert level == 0
        assert label == "Unknown"
        assert reason == ""

    def test_level_outside_range(self):
        level, label, reason = _parse_risk_response(
            "Level: 9\nLabel: High\nReason: Bad."
        )
        assert level == 0  # 9 is outside 1-5, so rejected
        assert label == "High"

    def test_level_zero_rejected(self):
        level, _, _ = _parse_risk_response("Level: 0")
        assert level == 0  # 0 is outside 1-5

    def test_case_insensitive(self):
        text = "level: 2\nlabel: low\nreason: looks fine."
        level, label, reason = _parse_risk_response(text)
        assert level == 2
        assert label == "Low"
        assert reason == "looks fine."

    def test_empty_string(self):
        level, label, reason = _parse_risk_response("")
        assert level == 0
        assert label == "Unknown"
        assert reason == ""


# ── _download_to_path ────────────────────────────────────────────── #


class TestDownloadToPath:
    def test_success(self, tmp_path):
        out = tmp_path / "img.jpg"
        fake_response = MagicMock()
        fake_response.read.return_value = b"\xff\xd8fake-image-data"
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            assert _download_to_path("http://example.com/img.jpg", out) is True
        assert out.read_bytes() == b"\xff\xd8fake-image-data"

    def test_empty_response_retries_and_fails(self, tmp_path):
        out = tmp_path / "img.jpg"
        fake_response = MagicMock()
        fake_response.read.return_value = b""
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            assert (
                _download_to_path(
                    "http://example.com/img.jpg", out, attempts=2
                )
                is False
            )

    def test_network_error_retries_and_fails(self, tmp_path):
        out = tmp_path / "img.jpg"
        with patch(
            "urllib.request.urlopen", side_effect=OSError("timeout")
        ):
            assert (
                _download_to_path(
                    "http://example.com/img.jpg", out, attempts=2
                )
                is False
            )


# ── _ollama_request ──────────────────────────────────────────────── #


class TestOllamaRequest:
    def test_get_request_returns_parsed_json(self):
        body = json.dumps({"models": []}).encode()
        fake_response = MagicMock()
        fake_response.read.return_value = body
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = _ollama_request("/api/tags")
        assert result == {"models": []}

    def test_post_request_sends_payload(self):
        body = json.dumps({"status": "ok"}).encode()
        fake_response = MagicMock()
        fake_response.read.return_value = body
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "urllib.request.urlopen", return_value=fake_response
        ) as mock_open:
            result = _ollama_request(
                "/api/generate", payload={"model": "test"}
            )
        assert result == {"status": "ok"}
        call_args = mock_open.call_args
        request_obj = call_args[0][0]
        assert request_obj.data is not None

    def test_network_error_raises_ollama_unavailable(self):
        with patch(
            "urllib.request.urlopen", side_effect=OSError("refused")
        ):
            with pytest.raises(OllamaUnavailableError):
                _ollama_request("/api/tags")

    def test_empty_response_returns_empty_dict(self):
        fake_response = MagicMock()
        fake_response.read.return_value = b"   "
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = _ollama_request("/api/tags")
        assert result == {}

    def test_invalid_json_returns_none(self):
        fake_response = MagicMock()
        fake_response.read.return_value = b"not-json-at-all"
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = _ollama_request("/api/tags")
        assert result is None


# ── _encode_image_for_ollama ─────────────────────────────────────── #


class TestEncodeImageForOllama:
    def test_returns_base64_string(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        result = _encode_image_for_ollama(img_path)
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_rgba_converted_to_rgb(self, tmp_path):
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img_path = tmp_path / "test.png"
        img.save(img_path)

        result = _encode_image_for_ollama(img_path)
        assert isinstance(result, str)


# ── _ollama_has_model ────────────────────────────────────────────── #


class TestOllamaHasModel:
    def test_model_found(self):
        tags = {"models": [{"name": "llava:latest"}]}
        with patch("app.ai_pipeline._ollama_request", return_value=tags):
            assert _ollama_has_model("llava:latest") is True

    def test_model_not_found(self):
        tags = {"models": [{"name": "llava:latest"}]}
        with patch("app.ai_pipeline._ollama_request", return_value=tags):
            assert _ollama_has_model("gemma:7b") is False

    def test_empty_tags(self):
        with patch("app.ai_pipeline._ollama_request", return_value=None):
            assert _ollama_has_model("llava:latest") is False

    def test_no_models_key(self):
        with patch("app.ai_pipeline._ollama_request", return_value={}):
            assert _ollama_has_model("llava:latest") is False


# ── _ensure_ollama_model ─────────────────────────────────────────── #


class TestEnsureOllamaModel:
    def test_already_present(self):
        with patch("app.ai_pipeline._ollama_has_model", return_value=True):
            assert _ensure_ollama_model("llava:latest") is True

    def test_pulls_when_missing_then_succeeds(self):
        with (
            patch(
                "app.ai_pipeline._ollama_has_model",
                side_effect=[False, True],
            ),
            patch("app.ai_pipeline._ollama_request") as mock_req,
        ):
            assert _ensure_ollama_model("llava:latest") is True
            mock_req.assert_called_once()

    def test_pulls_when_missing_and_still_fails(self):
        with (
            patch(
                "app.ai_pipeline._ollama_has_model",
                side_effect=[False, False],
            ),
            patch("app.ai_pipeline._ollama_request"),
        ):
            assert _ensure_ollama_model("llava:latest") is False


# ── fetch_satellite_image ────────────────────────────────────────── #


class TestFetchSatelliteImage:
    def test_invalid_input_returns_none(self):
        assert fetch_satellite_image(999, 0, 10) is None

    def test_cached_image_returns_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.ai_pipeline.IMAGE_DIR", tmp_path)
        path = tmp_path / "esri_10.000_20.000_z10.jpg"
        path.write_bytes(b"fake-jpg")
        with patch("app.ai_pipeline._image_filename", return_value=path):
            result = fetch_satellite_image(10.0, 20.0, 10)
        assert result == str(path)

    def test_download_success_first_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.ai_pipeline.IMAGE_DIR", tmp_path)
        out_path = tmp_path / "test.jpg"
        with (
            patch(
                "app.ai_pipeline._image_filename", return_value=out_path
            ),
            patch("app.ai_pipeline._download_to_path", return_value=True),
        ):
            result = fetch_satellite_image(10.0, 20.0, 10)
        assert result == str(out_path)

    def test_all_downloads_fail(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.ai_pipeline.IMAGE_DIR", tmp_path)
        out_path = tmp_path / "test.jpg"
        with (
            patch(
                "app.ai_pipeline._image_filename", return_value=out_path
            ),
            patch("app.ai_pipeline._download_to_path", return_value=False),
        ):
            result = fetch_satellite_image(10.0, 20.0, 10)
        assert result is None

    def test_fallback_to_tile_url(self, tmp_path, monkeypatch):
        """First URL fails, second (tile) URL succeeds."""
        monkeypatch.setattr("app.ai_pipeline.IMAGE_DIR", tmp_path)
        out_path = tmp_path / "test.jpg"
        with (
            patch(
                "app.ai_pipeline._image_filename", return_value=out_path
            ),
            patch(
                "app.ai_pipeline._download_to_path",
                side_effect=[False, True],
            ),
        ):
            result = fetch_satellite_image(10.0, 20.0, 10)
        assert result == str(out_path)

    def test_fallback_to_alt_tile_url(self, tmp_path, monkeypatch):
        """First two URLs fail, third (alt tile) URL succeeds."""
        monkeypatch.setattr("app.ai_pipeline.IMAGE_DIR", tmp_path)
        out_path = tmp_path / "test.jpg"
        with (
            patch(
                "app.ai_pipeline._image_filename", return_value=out_path
            ),
            patch(
                "app.ai_pipeline._download_to_path",
                side_effect=[False, False, True],
            ),
        ):
            result = fetch_satellite_image(10.0, 20.0, 10)
        assert result == str(out_path)


# ── _load_models_config ───────────────────────────────────────────── #


class TestLoadModelsConfig:
    def test_missing_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        assert _load_models_config() is None

    def test_valid_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  model: test-img\n  prompt: describe\n"
            "risk_classification:\n  model: test-risk\n  prompt: classify\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        result = _load_models_config()
        assert isinstance(result, ModelsConfig)
        assert result.image_description.model == "test-img"

    def test_invalid_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(": : : not valid yaml [[", encoding="utf-8")
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        assert _load_models_config() is None

    def test_non_dict_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text("- a list\n- not a dict\n", encoding="utf-8")
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        assert _load_models_config() is None


# ── config helpers ────────────────────────────────────────────────── #


class TestConfigHelpers:
    def test_image_description_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        model, prompt, options = _image_description_config()
        assert model == DEFAULT_IMAGE_MODEL
        assert prompt == DEFAULT_IMAGE_PROMPT
        assert options == DEFAULT_IMAGE_OPTIONS

    def test_risk_classification_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        model, prompt, options = _risk_classification_config()
        assert model == DEFAULT_RISK_MODEL
        assert prompt == DEFAULT_RISK_PROMPT
        assert options == DEFAULT_RISK_OPTIONS


class TestConfigFromYaml:
    def test_image_description_from_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  model: my-img-model\n  prompt: my prompt\n"
            "risk_classification:\n  model: my-risk\n  prompt: classify\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        model, prompt, options = _image_description_config()
        assert model == "my-img-model"
        assert prompt == "my prompt"

    def test_risk_classification_from_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  model: img\n  prompt: describe\n"
            "risk_classification:\n"
            "  model: my-risk\n  prompt: my classify\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        model, prompt, options = _risk_classification_config()
        assert model == "my-risk"
        assert prompt == "my classify"


# ── Pydantic model validation ────────────────────────────────────── #


class TestPydanticValidation:
    def test_valid_models_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n"
            "  model: test-img\n"
            "  prompt: describe\n"
            "risk_classification:\n"
            "  model: test-risk\n"
            "  prompt: classify\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        result = _load_models_config()
        assert isinstance(result, ModelsConfig)
        assert result.image_description.model == "test-img"
        assert result.risk_classification.model == "test-risk"

    def test_invalid_schema_returns_none(self, tmp_path, monkeypatch):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  wrong_key: value\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        result = _load_models_config()
        assert result is None

    def test_risk_result_defaults(self):
        r = RiskResult()
        assert r.danger_level == 0
        assert r.danger_label == "Unknown"

    def test_analysis_result_fields(self):
        a = AnalysisResult(
            description="test",
            danger_level=3,
            danger_label="Moderate",
        )
        dump = a.model_dump()
        assert dump["description"] == "test"
        assert dump["danger_level"] == 3


# ── Model name helpers ───────────────────────────────────────────── #


class TestModelNameHelpers:
    def test_get_image_model_name_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        assert get_image_model_name() == DEFAULT_IMAGE_MODEL

    def test_get_risk_model_name_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        assert get_risk_model_name() == DEFAULT_RISK_MODEL

    def test_get_image_model_display_name_from_config(
        self, tmp_path, monkeypatch
    ):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  model: img\n  prompt: p\n"
            "  display_name: My Image Model\n"
            "risk_classification:\n  model: risk\n  prompt: p\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        assert get_image_model_display_name() == "My Image Model"

    def test_get_image_model_display_name_fallback(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        assert get_image_model_display_name() == DEFAULT_IMAGE_MODEL

    def test_get_risk_model_display_name_from_config(
        self, tmp_path, monkeypatch
    ):
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "image_description:\n  model: img\n  prompt: p\n"
            "risk_classification:\n  model: risk\n  prompt: p\n"
            "  display_name: My Risk Model\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("app.ai_pipeline.MODELS_CONFIG_PATH", cfg)
        assert get_risk_model_display_name() == "My Risk Model"

    def test_get_risk_model_display_name_fallback(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "app.ai_pipeline.MODELS_CONFIG_PATH", tmp_path / "nope.yaml"
        )
        assert get_risk_model_display_name() == DEFAULT_RISK_MODEL

    def test_ollama_has_model_public(self):
        with patch("app.ai_pipeline._ollama_has_model", return_value=True):
            assert ollama_has_model("test") is True


# ── classify_risk (mock-based) ───────────────────────────────────── #


class TestClassifyRiskMocked:
    def test_returns_validated_dict(self):
        mock_response = {
            "response": "Level: 3\nLabel: Moderate\nReason: Some damage."
        }
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch(
                "app.ai_pipeline._ollama_request",
                return_value=mock_response,
            ),
        ):
            result = classify_risk("test description")
        assert result["danger_level"] == 3
        assert result["danger_label"] == "Moderate"
        assert "Some damage" in result["danger_reason"]

    def test_model_unavailable_returns_fallback(self):
        with patch(
            "app.ai_pipeline._ensure_ollama_model", return_value=False
        ):
            result = classify_risk("test")
        assert result["danger_level"] == 0
        assert result["danger_label"] == "Unknown"

    def test_ollama_returns_none(self):
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch("app.ai_pipeline._ollama_request", return_value=None),
        ):
            result = classify_risk("test description")
        assert result["danger_level"] == 0

    def test_empty_response_text(self):
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch(
                "app.ai_pipeline._ollama_request",
                return_value={"response": ""},
            ),
        ):
            result = classify_risk("test description")
        assert result["danger_level"] == 0

    def test_think_tags_stripped(self):
        response_text = (
            "<think>internal reasoning</think>"
            "Level: 4\nLabel: High\nReason: Severe damage visible."
        )
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch(
                "app.ai_pipeline._ollama_request",
                return_value={"response": response_text},
            ),
        ):
            result = classify_risk("test description")
        assert result["danger_level"] == 4
        assert result["danger_label"] == "High"


# ── analyze_image (mock-based) ───────────────────────────────────── #


class TestAnalyzeImageMocked:
    def test_missing_file_returns_error(self, tmp_path):
        result = analyze_image(str(tmp_path / "nonexistent.jpg"))
        assert result["description"] == "Image file not found or empty."
        assert result["danger_level"] == 0

    def test_empty_file_returns_error(self, tmp_path):
        empty_file = tmp_path / "empty.jpg"
        empty_file.write_bytes(b"")
        result = analyze_image(str(empty_file))
        assert "not found or empty" in result["description"]

    def test_model_unavailable(self, tmp_path):
        img = Image.new("RGB", (10, 10), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path)

        with patch(
            "app.ai_pipeline._ensure_ollama_model", return_value=False
        ):
            result = analyze_image(str(img_path))
        assert "Could not access Ollama" in result["description"]

    def test_ollama_returns_none(self, tmp_path):
        img = Image.new("RGB", (10, 10), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path)

        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch("app.ai_pipeline._ollama_request", return_value=None),
        ):
            result = analyze_image(str(img_path))
        assert "did not return a response" in result["description"]

    def test_successful_analysis(self, tmp_path):
        img = Image.new("RGB", (10, 10), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path)

        risk_result = {
            "danger_level": 2,
            "danger_label": "Low",
            "danger_reason": "Healthy vegetation.",
            "text_description": "Level: 2\nLabel: Low\nReason: Healthy.",
            "text_model": "test-model",
            "text_prompt": "test-prompt",
        }
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch(
                "app.ai_pipeline._ollama_request",
                return_value={"response": "Dense green canopy visible."},
            ),
            patch(
                "app.ai_pipeline.classify_risk", return_value=risk_result
            ),
        ):
            result = analyze_image(str(img_path))
        assert result["description"] == "Dense green canopy visible."
        assert result["danger_level"] == 2

    def test_empty_description_from_model(self, tmp_path):
        img = Image.new("RGB", (10, 10), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path)

        risk_result = RiskResult().model_dump()
        with (
            patch(
                "app.ai_pipeline._ensure_ollama_model", return_value=True
            ),
            patch(
                "app.ai_pipeline._ollama_request",
                return_value={"response": "   "},
            ),
            patch(
                "app.ai_pipeline.classify_risk", return_value=risk_result
            ),
        ):
            result = analyze_image(str(img_path))
        assert (
            result["description"]
            == "No description generated by the model."
        )


# ── pull_model_stream ────────────────────────────────────────────── #


class TestPullModelStream:
    def test_stream_events(self):
        lines = [
            json.dumps({"status": "pulling manifest"}).encode() + b"\n",
            json.dumps(
                {"status": "downloading", "total": 100, "completed": 50}
            ).encode()
            + b"\n",
            json.dumps({"status": "success"}).encode() + b"\n",
        ]
        fake_response = MagicMock()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.__iter__ = lambda s: iter(lines)

        with patch("urllib.request.urlopen", return_value=fake_response):
            events = list(pull_model_stream("test-model"))
        assert len(events) == 3
        assert events[-1]["status"] == "success"

    def test_network_error_yields_error(self):
        with patch(
            "urllib.request.urlopen", side_effect=OSError("refused")
        ):
            events = list(pull_model_stream("test-model"))
        assert len(events) == 1
        assert "error:" in events[0]["status"]

    def test_skips_empty_and_invalid_lines(self):
        lines = [
            b"\n",
            b"not-json\n",
            json.dumps({"status": "success"}).encode() + b"\n",
        ]
        fake_response = MagicMock()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.__iter__ = lambda s: iter(lines)

        with patch("urllib.request.urlopen", return_value=fake_response):
            events = list(pull_model_stream("test-model"))
        assert len(events) == 1
        assert events[0]["status"] == "success"


# ── save_analysis / load_previous_analysis ───────────────────────── #


class TestSaveAndLoad:
    def test_save_delegates_to_insert(self):
        with patch(
            "app.ai_pipeline.insert_analysis", return_value=True
        ) as mock:
            result = save_analysis(
                10.0, 20.0, 5, "img.jpg", {"test": True}
            )
        assert result is True
        mock.assert_called_once()

    def test_load_delegates_to_lookup(self):
        with patch(
            "app.ai_pipeline.lookup_analysis",
            return_value={"cached": True},
        ) as mock:
            result = load_previous_analysis(10.0, 20.0, 5)
        assert result == {"cached": True}
        mock.assert_called_once()
