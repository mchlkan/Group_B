# Group_B

A lightweight Python application for visualizing global environmental indicators on an interactive world map. Built as part of the **Advanced Programming** course hackathon at Nova SBE.

The tool automatically fetches the most recent environmental datasets from [Our World in Data](https://ourworldindata.org/), merges them with country geometries using GeoPandas, and presents the results through an interactive Streamlit dashboard.

Project Members:
* Michael Kania, 72782@novasbe.pt
* Leon Schmidt, 71644@novasbe.pt
* Matteo De Franceso, 71734@novasbe.pt
* Vanessa Weiss, 73217@novasbe.pt

---

## Project Structure

```
Group_B/
├── app/                  # Modular Python source code
├── downloads/            # Auto-generated folder for fetched datasets
├── notebooks/            # Prototyping and exploration notebooks
├── tests/                # Unit tests (pytest)
├── main.py               # Streamlit application entry point
├── requirements.txt      # pip dependencies
├── environment.yml       # Conda environment specification
├── .gitignore
└── README.md
```

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/mchlkan/Group_B.git
cd Group_B
```

### 2a. Setup with Conda (recommended)

```bash
conda env create -f environment.yml
conda activate <AdPro_Group-B>
```

### 2b. Setup with pip

```bash
python3.11 -m venv AdPro_Group-B
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```
