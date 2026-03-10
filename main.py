"""Project Okavango — Streamlit application entry point.

Multi-page navigation hub.  Run with::

    streamlit run main.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Project Okavango", layout="wide")

data_explorer = st.Page(
    "pages/1_Data_Explorer.py", title="Data Explorer", icon=":material/public:"
)
satellite_analysis = st.Page(
    "pages/2_Satellite_Analysis.py",
    title="Satellite Analysis",
    icon=":material/satellite_alt:",
)

pg = st.navigation([data_explorer, satellite_analysis])
pg.run()
