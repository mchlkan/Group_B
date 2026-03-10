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
- [ ] Real ESRI World Imagery download is implemented
- [x] Real Ollama image analysis is implemented
- [ ] Real Ollama danger/risk text analysis is implemented
- [x] `models.yaml` exists and is used by the app
- [ ] `database/images.csv` exists and is actively appended
- [ ] Cache/reuse logic exists (skip pipeline if settings already processed)
- [ ] README fully updated for Part II requirements
- [ ] Clean up repo

---

## Work Plan (What Is Still Missing)

## 1) AI Workflow — Task A: Image + Description

- [ ] Implement `fetch_satellite_image(latitude, longitude, zoom)` in `app/ai_pipeline.py`
- [ ] Use free ESRI World Imagery endpoint and save outputs to `images/`
- [ ] Create deterministic image filenames (for reproducibility and cache lookup)
- [ ] Implement `analyze_image(image_path)` with Ollama image-capable model
- [ ] Auto-pull missing model if not installed
- [ ] Return structured image output (`description`, `image_model`, `image_prompt`)
- [ ] Display image + generated description together in Streamlit

## 2) AI Workflow — Task B: Classification

- [ ] Implement second-step text risk analysis from description
- [ ] Define internal risk questions/prompt and classify environmental danger
- [ ] Return structured classification output (`danger_level`, `danger_label`, `danger_reason`)
- [ ] Display clear visual risk status in Streamlit (already scaffolded, needs real data)

## 3) Data Governance

- [ ] Add `models.yaml` at project root
- [ ] Store image model settings: model name, prompt, parameters
- [ ] Store text/risk model settings: model name, prompt, parameters
- [ ] Load `models.yaml` in the app and use it as single source of truth
- [ ] Create `database/` directory
- [ ] Create `database/images.csv` with required columns
- [ ] Append one row per run with timestamp + coords + zoom + models + prompts + outputs + danger
- [ ] Store image path/hash in CSV for traceability
- [ ] Before processing, check if same request already exists and reuse stored result
- [ ] If existing row found, skip model calls and display cached output

## 4) Repository Cleanup + Delivery

- [ ] Update README setup instructions (fresh clone -> run app)
- [ ] Add Ollama installation and model behavior notes
- [ ] Document `models.yaml` schema and required keys
- [ ] Document database format and caching behavior
- [ ] Add short SDG essay linking project to at least 3 UN SDGs
- [ ] Add 3 showcased examples of dangerous-area detections (image + output text)
- [ ] Verify all required files/folders are committed and paths work on clean clone

## 5) Quality Checks Before Final Submission

- [ ] Run `pytest` and fix failures
- [ ] Run style checks (`flake8`) and fix issues
- [ ] Verify app starts with `streamlit run main.py`
- [ ] Verify first run (new point) stores row and image
- [ ] Verify second run (same point/settings) uses cache and skips recompute
- [ ] Verify README instructions work exactly on a clean environment
