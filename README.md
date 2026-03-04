# Project Okavango — Group B

A lightweight Python application for visualising global environmental indicators on an interactive world map. Built as part of the **Advanced Programming** course at Nova SBE.

The tool automatically fetches the **most recent** environmental datasets from [Our World in Data](https://ourworldindata.org/), merges them with country geometries using GeoPandas, and presents the results through an interactive Streamlit dashboard powered by Plotly.

**Live Application:** [groupb-qtqrrbbvcdclxdhjzqcrtg.streamlit.app](https://groupb-qtqrrbbvcdclxdhjzqcrtg.streamlit.app/)

## Team

| Name                | Email                   |
|---------------------|-------------------------|
| Michael Kania       | 72782@novasbe.pt        |
| Leon Schmidt        | 71644@novasbe.pt        |
| Matteo De Francesco | 71734@novasbe.pt        |
| Vanessa Weiss       | 73217@novasbe.pt        |

---

## Datasets

All data is downloaded automatically at runtime — nothing is hardcoded.

| # | Dataset | Source |
|---|---------|--------|
| 1 | Annual Change in Forest Area | [ourworldindata.org/deforestation](https://ourworldindata.org/deforestation) |
| 2 | Annual Deforestation | [ourworldindata.org/deforestation](https://ourworldindata.org/deforestation) |
| 3 | Share of Protected Land | [ourworldindata.org/sdgs/life-on-land](https://ourworldindata.org/sdgs/life-on-land) |
| 4 | Share of Degraded Land | [ourworldindata.org/sdgs/life-on-land](https://ourworldindata.org/sdgs/life-on-land) |
| 5 | Share of Marine Protected Areas | [ourworldindata.org/sdgs/life-below-water](https://ourworldindata.org/sdgs/life-below-water) |
| Map | Natural Earth 110 m Admin 0 Countries | [naturalearthdata.com](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/) |

---

## Project Structure

```
Group_B/
├── app/
│   ├── __init__.py
│   ├── data.py            # OwidData class — data download, preprocessing, merging
│   └── ai_pipeline.py     # AI/satellite pipeline stubs (fetch, analyze, store)
├── pages/
│   ├── 1_Data_Explorer.py # Page 1 — interactive choropleth map and trend charts
│   └── 2_Satellite_Analysis.py  # Page 2 — satellite imagery + AI analysis UI
├── downloads/              # Auto-generated folder for fetched datasets & shapefiles
├── notebooks/              # Prototyping and exploration notebooks
├── tests/                  # Unit tests (pytest)
├── main.py                 # Streamlit multi-page navigation entry point
├── requirements.txt        # pip dependencies
├── setup.cfg               # Linter configuration (flake8)
├── .gitignore
├── LICENSE
└── README.md
```

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/mchlkan/Group_B.git
cd Group_B
```

### 2. Create a Virtual Environment and Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 3. Run the Application

```bash
streamlit run main.py
```

The dashboard will open in your browser (default: <http://localhost:8501>).

### 4. Run Tests

```bash
pytest
```

---

## How It Works

### Data layer — `app/data.py`

The `OwidData` class drives the entire data pipeline:

1. Downloads the five OWID CSV datasets and the Natural Earth 110 m shapefile into `downloads/` (skipped if already present).
2. Preprocesses each dataset — validates columns, auto-detects the metric column, and adds `is_aggregate` / `is_mappable` boolean flags.
3. Merges all datasets with country geometries via GeoPandas to produce a single `GeoDataFrame` per dataset ready for mapping.

### AI pipeline — `app/ai_pipeline.py`

Defines the backend interface for the Satellite Analysis page:

| Function | Purpose |
|---|---|
| `fetch_satellite_image(lat, lon, zoom)` | Download a satellite tile and return its local path |
| `analyze_image(image_path)` | Send the image to an AI/LLM and return a description + danger level (1–5) |
| `save_analysis(...)` | Persist an analysis result to a database |
| `load_previous_analysis(lat, lon)` | Retrieve a stored analysis for a given coordinate |

> All functions are currently **stubs** — they return placeholder data so the UI renders. Teammates implement the bodies (Ollama calls, tile servers, database writes, etc.).

### Application — `main.py` + `pages/`

`main.py` is the Streamlit multi-page navigation hub. It registers two pages and delegates rendering to each:

**Page 1 — Data Explorer** (`pages/1_Data_Explorer.py`)
- `load_data()` — loads and caches the `OwidData` instance.
- `_render_kpis()` — displays key indicators (countries with data, global mean, highest, lowest).
- `_render_bar_chart()` — top-5 / bottom-5 countries bar chart; click a bar to select a country.
- `_render_details_and_trend()` — per-country metric cards and a time-series line chart.
- `page()` — assembles the full layout: sidebar controls (dataset, year, region), choropleth map, and the panels above.

**Page 2 — Satellite Analysis** (`pages/2_Satellite_Analysis.py`)
- `page()` — coordinate input form, triggers `fetch_satellite_image` and `analyze_image`.
- `_danger_badge()` — renders a colour-coded HTML badge for the AI danger level.
- `_render_placeholder()` — shown while awaiting a real satellite image.
- `_render_result()` — displays the AI description, danger score, and any stored history.

---

## Requirements

- Python ≥ 3.11
- See [requirements.txt](requirements.txt) for package versions:
  - `geopandas >=1.0, <2.0`
  - `pandas >=2.0, <3.0`
  - `plotly >=5.0, <6.0`
  - `streamlit >=1.35, <2.0`

---

## License

This project is licensed under the [MIT License](LICENSE).
