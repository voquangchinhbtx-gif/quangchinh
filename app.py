import streamlit as st
import requests
import math
from datetime import datetime
from database import load_data, add_plant, delete_plant, add_chat

# ==============================
# CẤU HÌNH API
# ==============================

API_KEY = "66ad043d6024749fa4bf92f0a6782397"

# Tọa độ Huế
LAT = 16.4637
LON = 107.5909


# ==============================
# TÍNH VPD
# ==============================

def calculate_vpd(temp, humidity):
    """Tính thâm hụt áp suất hơi nước (VPD)"""

    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)

    return svp - avp


# ==============================
# LẤY THỜI TIẾT
# ==============================

def get_real_weather():

    url = (
        "http://api.openweathermap.org/data/2.5/weather"
        f"?lat={LAT}&lon={LON}"
        f"&appid={API_KEY}"
        "&units=metric&lang=vi"
    )

    try:

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json()

        return {
            "temp": data["main"]["temp"],
            "hum": data["main"]["humidity"],
            "rain": data.get("rain", {}).get("1h", 0),
            "desc": data["weather"][0]["description"]
        }

    except Exception:
        return None


# ==============================
# PHÂN TÍCH CẢNH BÁO
# ==============================

def get_expert_warnings(temp, hum, rain):

    warnings = []

    vpd = calculate_vpd(temp, hum)

    # Kịch bản nấm
    if vpd < 0.5 and 20 <= temp <= 28:

        warnings.append({
            "title": "🔴 NGUY CƠ NẤM CAO",
            "analysis": f"VPD thấp ({vpd:.2f} kPa). Không khí bão hòa, nấm dễ phát triển.",
            "action": "Tỉa lá cho thoáng, tránh tưới ban đêm."
        })

    # Kịch bản vi khuẩn
    if temp > 31 and hum > 80 and rain > 0:

        warnings.append({
            "title": "🆘 VI KHUẨN THỐI NHŨN",
            "analysis": "Nắng nóng sau mưa dễ gây nứt mô thực vật.",
            "action": "Rải vôi sát khuẩn hoặc dùng chế phẩm sinh học."
        })

    return warnings, vpd


# ==============================
# CẤU HÌNH TRANG
# ==============================

st.set_page_config(
    page_title="Aji Farm Pro",
    layout="wide",
    page_icon="🌶️"
)

data = load_data()


# ==============================
# SIDEBAR
# ==============================

with st.sidebar:

    st.title("🌶️ Aji Farm AI")

    menu = st.radio(
        "Menu",
        [
            "📊 Dashboard Chuyên sâu",
            "🌱 Quản lý Cây trồng",
            "💬 AI Assistant"
        ]
    )


# ==============================
# DASHBOARD
# ==============================

if menu == "📊 Dashboard Chuyên sâu":

    st.title("📊 Hệ thống Quan trắc & Dự báo Dịch hại")

    weather = get_real_weather()

    if weather:

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Nhiệt độ", f"{weather['temp']} °C")
        col2.metric("Độ ẩm", f"{weather['hum']} %")
        col3.metric("Mưa", f"{weather['rain']} mm")
        col4.metric("Thời tiết", weather["desc"].capitalize())

        st.markdown("---")

        alerts, vpd = get_expert_warnings(
            weather["temp"],
            weather["hum"],
            weather["rain"]
        )

        col_vpd, col_alert = st.columns([1, 2])

        with col_vpd:

            st.subheader("Chỉ số VPD")

            st.info(f"Hiện tại: {vpd:.2f} kPa")

            if vpd < 0.5:

                st.error("Mức độ: Nguy hiểm cao")

            elif 0.8 <= vpd <= 1.2:

                st.success("Mức độ: Lý tưởng")

            else:

                st.warning("Mức độ: Stress nhiệt")

        with col_alert:

            st.subheader("Cảnh báo thực địa")

            if not alerts:

                st.success("Hệ sinh thái đang ở trạng thái an toàn.")

            else:

                for alert in alerts:

                    with st.container(border=True):

                        st.error(f"**{alert['title']}**")

                        st.write(f"🔬 {alert['analysis']}")

                        st.warning(f"💡 {alert['action']}")

    else:

        st.error("Không lấy được dữ liệu thời tiết từ API.")


# ==============================
# QUẢN LÝ CÂY
# ==============================

elif menu == "🌱 Quản lý Cây trồng":

    st.title("🌱 Quản lý Vườn")

    # --- THÊM CÂY ---
    with st.expander("➕ Thêm cây mới"):

        name = st.text_input("Tên cây")

        date = st.date_input("Ngày trồng")

        if st.button("Xác nhận lưu"):

            name = name.strip()

            if name == "":

                st.warning("⚠️ Vui lòng nhập tên cây")

            else:

                plant_date = date.isoformat()

                # kiểm tra trùng
                exists = any(
                    p["name"].lower() == name.lower()
                    and p["date"] == plant_date
                    for p in data["plants"]
                )

                if exists:

                    st.warning("⚠️ Cây này đã tồn tại")

                else:

                    data = add_plant(data, name, plant_date)

                    st.success("✅ Đã thêm cây thành công")

                    st.rerun()

    # --- DANH SÁCH CÂY ---

    plants = data.get("plants", [])

    if plants:

        cols = st.columns(3)

        for i, p in enumerate(plants):

            with cols[i % 3]:

                with st.container(border=True):

                    st.subheader(f"🌿 {p['name']}")

                    st.caption(
                        f"🆔 ID: {p['id']} | 📅 Ngày trồng: {p['date']}"
                    )

                    if st.button(
                        f"Xóa cây {p['id']}",
                        key=f"delete_{p['id']}"
                    ):

                        data = delete_plant(data, p["id"])

                        st.rerun()

    else:

        st.info("Chưa có cây nào trong hệ thống.")


# ==============================
# AI ASSISTANT
# ==============================

elif menu == "💬 AI Assistant":

    st.title("💬 Trợ lý Nông nghiệp AI")

    for chat in data["chat_history"]:

        with st.chat_message("user"):

            st.write(chat["user"])

        with st.chat_message("assistant"):

            st.write(chat["ai"])

    if prompt := st.chat_input("Hỏi gì đó về cây trồng..."):

        with st.chat_message("user"):

            st.write(prompt)

        # Tạm thời AI giả lập
        ai_response = "AI đang phân tích dữ liệu nông nghiệp..."

        data = add_chat(data, prompt, ai_response)

        with st.chat_message("assistant"):

            st.write(ai_response)
