# Project Plan — Group B: Project Okavango (Phase II)

**Deadline:** March 20, 2026 23:59:59

---

## Goal of This Phase

Scale the app with a working AI workflow (satellite image -> image description -> environmental risk classification), add governance/configuration, and finalize a clean, documented repository.

---

## Current Status Snapshot

- [x] Streamlit Page 2 (`pages/2_Satellite_Analysis.py`)
- [x] Coordinate + zoom inputs 
- [x] Clickable map for coordinate selection
- [x] Real ESRI World Imagery download is implemented
- [x] Real Ollama image analysis is implemented
- [x] Real Ollama danger/risk text analysis is implemented
- [x] `models.yaml` exists and is used by the app
- [x] Database persistence via SQLite (`database/okavango.db`) — replaced `images.csv` with a more robust relational store
- [x] Cache/reuse logic exists (skip pipeline if settings already processed)
- [x] README fully updated for Part II requirements
- [x] Clean up repo

---

## Work Plan (What Is Still Missing)

## 1) AI Workflow — Task A: Image + Description

- [x] Implement `fetch_satellite_image(latitude, longitude, zoom)` in `app/ai_pipeline.py`
- [x] Use free ESRI World Imagery endpoint and save outputs to `images/`
- [x] Create deterministic image filenames (for reproducibility and cache lookup)
- [x] Implement `analyze_image(image_path)` with Ollama image-capable model
- [x] Auto-pull missing model if not installed
- [x] Return structured image output (`description`, `image_model`, `image_prompt`)
- [x] Display image + generated description together in Streamlit

## 2) AI Workflow — Task B: Classification

- [x] Implement second-step text risk analysis from description
- [x] Define internal risk questions/prompt and classify environmental danger
- [x] Return structured classification output (`danger_level`, `danger_label`, `danger_reason`)
- [x] Display clear visual risk status in Streamlit (already scaffolded, needs real data)

## 3) Data Governance

- [x] Add `models.yaml` at project root
- [x] Store image model settings: model name, prompt, parameters
- [x] Store text/risk model settings: model name, prompt, parameters
- [x] Load `models.yaml` in the app and use it as single source of truth
- [x] Create `database/` directory
- [x] SQLite database (`database/okavango.db`) with full schema — replaced CSV with relational store
- [x] Append one row per run with timestamp + coords + zoom + models + prompts + outputs + danger
- [x] Store image path in database for traceability
- [x] Before processing, check if same request already exists and reuse stored result (`lookup_analysis()`)
- [x] If existing row found, skip model calls and display cached output

## 4) Repository Cleanup + Delivery

- [x] Update README setup instructions (fresh clone -> run app)
- [x] Add Ollama installation and model behavior notes
- [x] Document `models.yaml` schema and required keys
- [x] Document database format and caching behavior
- [x] Add short SDG essay linking project to at least 3 UN SDGs
- [x] Add 3 showcased examples of dangerous-area detections (image + output text)
- [x] Verify all required files/folders are committed and paths work on clean clone

## 5) Quality Checks Before Final Submission

- [x] Run `pytest` and fix failures — 61/61 passing
- [x] Run style checks (`flake8`) and fix issues — clean
- [x] Verify app starts with `streamlit run main.py`
- [x] Verify first run (new point) stores row and image
- [x] Verify second run (same point/settings) uses cache and skips recompute
- [x] Verify README instructions work exactly on a clean environment
