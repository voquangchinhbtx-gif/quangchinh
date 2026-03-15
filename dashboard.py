import streamlit as st
import pandas as pd
from database import get_plants
from crop_database import get_crop_info


def show_dashboard(data, weather):

    st.title("🌤 Tổng quan nông trại")

    col1, col2, col3 = st.columns(3)

    col1.metric("🌡 Nhiệt độ", weather["temp"])
    col2.metric("💧 Độ ẩm", weather["hum"])
    col3.metric("🌬 Gió", weather["wind"])

    plants = get_plants(data)

    st.metric("🌱 Tổng cây", len(plants))

    if plants:

        names = [get_crop_info(p["crop"])["name"] for p in plants]

        df = pd.DataFrame({"Cây": names})

        st.bar_chart(df["Cây"].value_counts())

