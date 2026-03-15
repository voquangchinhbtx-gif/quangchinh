import streamlit as st
from PIL import Image
from gemini_ai import load_model, diagnose
from npk_ai import analyze_leaf_npk


def show_ai_doctor():

    st.title("🦠 AI Bác sĩ cây")

    api = st.text_input("Gemini API", type="password")

    img_file = st.file_uploader("Chụp lá cây")

    if img_file:

        image = Image.open(img_file)

        st.image(image, width=300)

        st.subheader("🌿 Phân tích dinh dưỡng")

        result = analyze_leaf_npk(image)

        st.success(result)

        if api:

            model = load_model(api)

            if st.button("Phân tích bệnh bằng AI"):

                r = diagnose(model, image)

                st.write(r)

