import pandas as pd
import streamlit as st
import geopandas as gpd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class OwidData:
    def __init__(self):
        self.STORAGE_OPTIONS = {'User-Agent': 'Our World In Data data fetch/1.0'}

        self.df_world = gpd.read_file("https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip")
        self.datasets = {
            "Annual Change In Forest Area":  self.merge_map(data=pd.read_csv("https://ourworldindata.org/grapher/annual-change-forest-area.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Annual Change In Forest Area'),
            "Annual Deforestation": self.merge_map(data=pd.read_csv("https://ourworldindata.org/grapher/annual-deforestation.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Annual Deforestation'),
            "Share Of Protected Land": self.merge_map(data=pd.read_csv("https://ourworldindata.org/grapher/terrestrial-protected-areas.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Share Of Protected Land'),
            "Share Of Degraded Land": self.merge_map(data=pd.read_csv("https://ourworldindata.org/grapher/share-degraded-land.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Share Of Degraded Land'),
            #"fifth_dataset": "PUT_YOUR_DF_HERE"  # replace with the fifth dataset
        }
        self.move_to_downloads()

    def move_to_downloads(self):
        for dataset_name,dataset_file in self.datasets.items():
            output_path = BASE_DIR / "downloads" / f"{dataset_name}.csv"
            dataset_file.to_csv(output_path, index=False)
        self.df_world.to_csv(BASE_DIR / "downloads" / "world.csv", index=False)

    def merge_map(self, data, varname):
        df_clean = data[(~data.code.isnull()) & (data.code != 'OWID_WRL')]
        df_clean.rename(columns={df_clean.columns[-1]: varname}, inplace=True)
        merged_df = pd.merge(self.df_world, df_clean, left_on='ISO_A3', right_on='code', how='right')
        return merged_df[["geometry", "NAME", "SOVEREIGNT", "CONTINENT", "REGION_UN", "SUBREGION", "REGION_WB", "ECONOMY","INCOME_GRP", f"{varname}", "year", 'entity']]

tool_data = OwidData()

st.title('Test Title this tests the title')
selbox_text = st.selectbox(options  = tool_data.datasets.keys(), label ='a select box?')
df_displayed = tool_data.datasets[selbox_text]
target_year = st.select_slider(options=range(df_displayed.year.min(),df_displayed.year.max()), label = 'year')
st.text(f'This graph shows {selbox_text} in the year {target_year}')

df_displayed = df_displayed[df_displayed.year == target_year].groupby('entity')[df_displayed.columns[-1]].mean()
st.bar_chart(df_displayed)
st.text(f'the select box says: {selbox_text}')