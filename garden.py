import streamlit as st
from datetime import date
from database import add_plant, save_data
from crop_database import CROPS


def show_garden(data):

    st.title("🌱 Quản lý vườn")

    crop = st.selectbox("Chọn cây", list(CROPS.keys()))

    plant_date = st.date_input("Ngày trồng", date.today())

    if st.button("Thêm cây"):

        add_plant(data, {
            "crop": crop,
            "date": plant_date.strftime("%Y-%m-%d")
        })

        save_data(data)

        st.success("Đã thêm cây")

