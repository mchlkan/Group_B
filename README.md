# Project Okavango — Group B

A lightweight Python application for visualising global environmental indicators on an interactive world map. Built as part of the **Advanced Programming** course hackathon at Nova SBE.

The tool automatically fetches the **most recent** environmental datasets from [Our World in Data](https://ourworldindata.org/), merges them with country geometries using GeoPandas, and presents the results through an interactive Streamlit dashboard powered by Plotly.

**Live demo:** [groupb-qtqrrbbvcdclxdhjzqcrtg.streamlit.app](https://groupb-qtqrrbbvcdclxdhjzqcrtg.streamlit.app/)

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
│   └── data.py            # OwidData class (data pipeline)
├── downloads/              # Auto-generated folder for fetched datasets
├── notebooks/              # Prototyping and exploration notebooks
├── tests/                  # Unit tests (pytest)
├── main.py                 # Streamlit application entry point
├── requirements.txt        # pip dependencies
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

1. **`OwidData` class** (`app/data.py`) — downloads the five OWID CSV datasets and the Natural Earth shapefile into `downloads/`, preprocesses each dataset (validates columns, detects the metric column, adds `is_aggregate` / `is_mappable` flags), and merges them with country geometries.
2. **`main.py`** — imports `OwidData`, caches it with `@st.cache_resource`, and builds the Streamlit dashboard:
   - **Sidebar controls**: dataset selector, year slider, region filter.
   - **Key indicators**: countries with data, global mean, highest, lowest.
   - **Choropleth map**: interactive Plotly map; click a country to inspect it.
   - **Selection details & trend**: country metrics and a time-series line chart scoped to the selected year.
   - **Global trend**: top-5 / bottom-5 bar chart; click a bar to select that country.

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
