"""Unit tests for app.ai_pipeline — pure functions only (no Ollama needed)."""

from __future__ import annotations

from unittest.mock import patch

from app.ai_pipeline import (DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_OPTIONS,
                             DEFAULT_IMAGE_PROMPT, DEFAULT_RISK_MODEL,
                             DEFAULT_RISK_OPTIONS, DEFAULT_RISK_PROMPT,
                             IMAGE_DIR, AnalysisResult, ModelsConfig,
                             RiskResult, _bbox_for_coordinate,
                             _image_description_config, _image_filename,
                             _is_valid_input, _load_models_config,
                             _parse_risk_response, _risk_classification_config,
                             _tile_xy_from_latlon, analyze_image,
                             classify_risk)

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


# ── Public API (mock-based) ──────────────────────────────────────── #


class TestClassifyRiskMocked:
    def test_returns_validated_dict(self):
        mock_response = {
            "response": "Level: 3\nLabel: Moderate\nReason: Some damage."
        }
        with (
            patch("app.ai_pipeline._ensure_ollama_model", return_value=True),
            patch(
                "app.ai_pipeline._ollama_request", return_value=mock_response
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


class TestAnalyzeImageMocked:
    def test_missing_file_returns_error(self, tmp_path):
        result = analyze_image(str(tmp_path / "nonexistent.jpg"))
        assert result["description"] == "Image file not found or empty."
        assert result["danger_level"] == 0
