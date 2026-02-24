import pandas as pd
import streamlit as st
import geopandas as gpd
from pathlib import Path
import folium
from streamlit_folium import st_folium

BASE_DIR = Path(__file__).resolve().parent

class OwidData:
    def __init__(self):
        self.STORAGE_OPTIONS = {'User-Agent': 'Our World In Data data fetch/1.0'}

        self.df_world = gpd.read_file("https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip")
        self.datasets = {
            "Annual Change In Forest Area":  self.clean_merge_drop_nulls(data=pd.read_csv("https://ourworldindata.org/grapher/annual-change-forest-area.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Annual Change In Forest Area'),
            "Annual Deforestation": self.clean_merge_drop_nulls(data=pd.read_csv("https://ourworldindata.org/grapher/annual-deforestation.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Annual Deforestation'),
            "Share Of Protected Land": self.clean_merge_drop_nulls(data=pd.read_csv("https://ourworldindata.org/grapher/terrestrial-protected-areas.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Share Of Protected Land'),
            "Share Of Degraded Land": self.clean_merge_drop_nulls(data=pd.read_csv("https://ourworldindata.org/grapher/share-degraded-land.csv?v=1&csvType=full&useColumnShortNames=true", storage_options = self.STORAGE_OPTIONS), varname='Share Of Degraded Land'),
            #"fifth_dataset": "PUT_YOUR_DF_HERE"  # replace with the fifth dataset
        }
        self.move_to_downloads()

    def move_to_downloads(self):
        for dataset_name,dataset_file in self.datasets.items():
            output_path = BASE_DIR / "downloads" / f"{dataset_name}.csv"
            dataset_file.to_csv(output_path, index=False)
        self.df_world.to_csv(BASE_DIR / "downloads" / "world.csv", index=False)

    def clean_merge_drop_nulls(self, data, varname):
        df_clean = data[(~data.code.isnull()) & (data.code != 'OWID_WRL')]
        df_clean.rename(columns={df_clean.columns[-1]: varname}, inplace=True)
        merged_df = pd.merge(self.df_world, df_clean, left_on='ISO_A3', right_on='code', how='right')
        return merged_df[["geometry", "NAME", "SOVEREIGNT", "CONTINENT", "REGION_UN", "SUBREGION", "REGION_WB", "ECONOMY","INCOME_GRP", f"{varname}", "year", 'entity']].dropna()

class WebApp(OwidData):
    def __init__(self):
        super().__init__()
        self.selected_varname, self.selected_region = self.ui_setup()
        self.selected_df = self.datasets[self.selected_varname]
        self.selected_year = st.select_slider(options= self.selected_df.year.unique(), label='Year')


    def ui_setup(self):
        st.title('Group B\'s ADPro 2026 Project')
        st.text('')
        col1, col2 = st.columns([2, 2])

        with col1:
            selbox_text = st.selectbox(
                "Select dataset",
                self.datasets.keys())
        regions = list(self.datasets[selbox_text].REGION_UN.unique())
        regions.append('World')
        with col2:
            region = st.selectbox(
                "Region",
                options=regions)

        return selbox_text, region

    def display_map(self):

        st.text('Map map this is an empty placeholder map look at this map')
        m = folium.Map(
            location=[20, 0],
            zoom_start=2,
            tiles="CartoDB positron"
        )
        st_folium(m, width=700, height=500)

    def display_graph(self):
        st.text(f'This graph shows {self.selected_varname} by {self.selected_region} in the year {self.selected_year}')
        if self.selected_region == 'World':
            data_displayed = self.selected_df[(self.selected_df.year == self.selected_year)].groupby('entity')[self.selected_varname].mean()
            st.bar_chart(data_displayed)

        else:
            data_displayed = self.selected_df[(self.selected_df.year == self.selected_year) & (self.selected_df.REGION_UN == self.selected_region)].groupby('entity')[
                self.selected_varname].mean()
            st.bar_chart(data_displayed)


app = WebApp()
app.display_map()
app.display_graph()