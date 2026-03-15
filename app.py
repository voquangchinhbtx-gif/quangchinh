import streamlit as st
import requests
import math
from datetime import datetime
from database import load_data, add_plant, delete_plant, add_chat

# =========================
# CẤU HÌNH HỆ THỐNG
# =========================

API_KEY = "66ad043d6024749fa4bf92f0a6782397"

LAT = 16.4637
LON = 107.5909   # Huế


# =========================
# TÍNH CHỈ SỐ VPD
# =========================

def calculate_vpd(temp, humidity):
    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)
    return svp - avp


# =========================
# LẤY DỮ LIỆU THỜI TIẾT
# =========================

def get_real_weather():

    url = f"http://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric&lang=vi"

    try:

        res = requests.get(url, timeout=10)

        if res.status_code == 200:

            d = res.json()

            return {
                "temp": d["main"]["temp"],
                "hum": d["main"]["humidity"],
                "rain": d.get("rain", {}).get("1h", 0),
                "desc": d["weather"][0]["description"]
            }

    except:
        pass

    return None


# =========================
# TRI THỨC CÂY TRỒNG
# =========================

CROP_KNOWLEDGE = {

    "Ớt Aji Charapita": {
        "guide": "Cần nắng 6-8h/ngày. Tưới giữ ẩm nhưng tránh úng. Bón phân hữu cơ 15 ngày/lần.",
        "harvest_day": 90,
        "warning": "Dễ bị nhện đỏ khi trời khô nóng."
    },

    "Sầu riêng": {
        "guide": "Cần đất thoát nước tốt. Cây con cần che bóng 50%.",
        "harvest_day": 1500,
        "warning": "Chú ý nấm Phytophthora khi mưa nhiều."
    },

    "Cà chua": {
        "guide": "Cần làm giàn sớm. Tưới nước vào gốc, tránh ướt lá.",
        "harvest_day": 75,
        "warning": "Bón quá nhiều đạm sẽ ít quả."
    },

    "Rau cải": {
        "guide": "Tưới phun sương sáng/chiều. Thu hoạch nhanh.",
        "harvest_day": 35,
        "warning": "Chú ý sâu xanh ăn lá."
    }

}


# =========================
# CẤU HÌNH STREAMLIT
# =========================

st.set_page_config(
    page_title="Aji Farm Pro AI",
    layout="wide",
    page_icon="🌱"
)

data = load_data()

# Chỉ gọi API 1 lần
weather = get_real_weather()


# =========================
# SIDEBAR
# =========================

with st.sidebar:

    st.title("🌶️ Aji Farm AI Pro")

    menu = st.radio(
        "Hệ thống quản trị",
        [
            "📊 Dashboard Dự báo",
            "🌱 Quản lý Vườn & Quy trình",
            "💬 Trợ lý AI Assistant"
        ]
    )


# =========================
# DASHBOARD
# =========================

if menu == "📊 Dashboard Dự báo":

    st.title("📊 Quan trắc VPD & Dịch hại")

    if weather and weather.get("temp"):

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("🌡 Nhiệt độ", f"{weather['temp']}°C")
        c2.metric("💧 Độ ẩm", f"{weather['hum']}%")
        c3.metric("🌧 Lượng mưa", f"{weather['rain']} mm")
        c4.metric("🌤 Trạng thái", weather['desc'].capitalize())

        vpd = calculate_vpd(weather['temp'], weather['hum'])

        st.markdown(f"### Chỉ số VPD hiện tại: `{vpd:.2f} kPa`")

        st.caption(
            "VPD (Vapor Pressure Deficit) thể hiện khả năng thoát hơi nước của cây. "
            "VPD thấp → độ ẩm cao → nấm bệnh dễ phát triển. "
            "VPD cao → không khí khô → cây stress và nhện đỏ dễ xuất hiện."
        )

        if vpd < 0.5:
            st.error("🔴 Độ ẩm quá cao → nguy cơ nấm bệnh.")

        elif vpd > 2.0:
            st.warning("🟠 Không khí khô → nguy cơ nhện đỏ.")

        else:
            st.success("🟢 Điều kiện tốt cho quang hợp.")

    else:

        st.error("Không lấy được dữ liệu thời tiết.")


# =========================
# QUẢN LÝ CÂY TRỒNG
# =========================

elif menu == "🌱 Quản lý Vườn & Quy trình":

    st.title("🌱 Vòng đời Cây trồng")

    with st.expander("➕ Thêm cây mới"):

        c1, c2 = st.columns(2)

        with c1:
            name = st.text_input("Tên cây")
            crop_type = st.selectbox(
                "Chọn giống cây",
                list(CROP_KNOWLEDGE.keys()) + ["Khác"]
            )

        with c2:
            date = st.date_input("Ngày trồng")

        if st.button("Kích hoạt quy trình chăm sóc"):

            if name.strip() == "":
                st.warning("Vui lòng nhập tên cây")

            else:

                data = add_plant(
                    data,
                    f"{name} ({crop_type})",
                    date.strftime("%Y-%m-%d")
                )

                st.success("Đã thêm cây")

                st.rerun()

    plants = data.get("plants", [])

    if not plants:

        st.info("Chưa có cây trồng.")

    else:

        st.write(f"### Có {len(plants)} cây đang theo dõi")

        for p in plants:

            with st.container(border=True):

                col_info, col_ai, col_action = st.columns([1,2,1])

                with col_info:

                    st.subheader(f"🌿 {p['name']}")

                    st.caption(f"ID: {p['id']} | Trồng ngày: {p['date']}")

                    try:
                        age = (
                            datetime.now() -
                            datetime.strptime(p['date'], "%Y-%m-%d")
                        ).days

                        st.write(f"Tuổi cây: {age} ngày")

                    except:
                        pass

                with col_ai:

                    st.markdown("**Quy trình chăm sóc:**")

                    knowledge = next(
                        (v for k, v in CROP_KNOWLEDGE.items() if k in p['name']),
                        None
                    )

                    if knowledge:

                        st.info(knowledge["guide"])
                        st.warning(f"Lưu ý: {knowledge['warning']}")

                    else:

                        st.info("Đang cập nhật quy trình...")

                    if weather and weather["temp"] > 32:

                        st.error("AI cảnh báo: Trời nóng, nên tưới chiều.")

                with col_action:

                    if st.button(
                        "Thu hoạch / Xóa",
                        key=f"del_{p['id']}",
                        use_container_width=True
                    ):

                        data = delete_plant(data, p["id"])

                        st.balloons()

                        st.rerun()


# =========================
# AI ASSISTANT
# =========================

elif menu == "💬 Trợ lý AI Assistant":

    st.title("💬 Trợ lý Nông nghiệp")

    total_plants = len(data.get("plants", []))

    if weather:

        st.info(
            f"Hệ thống đang theo dõi {total_plants} cây trồng. "
            f"Nhiệt độ hiện tại {weather['temp']}°C, độ ẩm {weather['hum']}%."
        )

    else:

        st.info(
            f"Hệ thống đang theo dõi {total_plants} cây trồng trong vườn."
        )

    for chat in data.get("chat_history", []):

        with st.chat_message("user"):
            st.write(chat["user"])

        with st.chat_message("assistant"):
            st.write(chat["ai"])

    if prompt := st.chat_input("Hỏi về bón phân, sâu bệnh..."):

        with st.chat_message("user"):
            st.write(prompt)

        if weather:

            ai_res = f"Nhiệt độ hiện tại {weather['temp']}°C, độ ẩm {weather['hum']}%. "

            if weather["temp"] > 30:
                ai_res += "Trời khá nóng, nên tăng tưới nước và chú ý nhện đỏ."

            elif weather["hum"] > 85:
                ai_res += "Độ ẩm cao, nên phòng nấm bệnh."

            else:
                ai_res += "Điều kiện thời tiết khá thuận lợi."

        else:

            ai_res = "Hiện chưa lấy được dữ liệu thời tiết."

        data = add_chat(data, prompt, ai_res)

        with st.chat_message("assistant"):
            st.write(ai_res)
