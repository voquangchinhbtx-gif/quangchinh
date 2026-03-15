import streamlit as st
from streamlit_js_eval import get_geolocation

from database import load_data
from weather import get_weather
from dashboard import show_dashboard
from garden import show_garden
from ai_doctor import show_ai_doctor

data = load_data()

st.sidebar.title("🌶 Aji Farm AI")

menu = st.sidebar.radio(

    "Menu",

    ["Dashboard", "Quản lý vườn", "AI Doctor"]

)

geo = get_geolocation()

if geo and "coords" in geo:

    lat = geo["coords"]["latitude"]
    lon = geo["coords"]["longitude"]

else:

    lat = 16.47
    lon = 107.58

weather = get_weather(lat, lon)

if menu == "Dashboard":

    show_dashboard(data, weather)

elif menu == "Quản lý vườn":

    show_garden(data)

elif menu == "AI Doctor":

    show_ai_doctor()

