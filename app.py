import streamlit as st
import requests
import math
from datetime import datetime
from database import load_data, add_plant, delete_plant, add_chat

# =========================
# CẤU HÌNH
# =========================

# Sử dụng st.secrets để bảo mật API Key khi triển khai
try:
    API_KEY = st.secrets["OPENWEATHER_API_KEY"]
except:
    # Key dự phòng nếu không tìm thấy trong secrets
    API_KEY = "66ad043d6024749fa4bf92f0a6782397"
    LAT, LON = 16.4637, 107.5909  # Tọa độ của Huế
# Cấu hình Gemini AI (Dành cho nhận diện hình ảnh)
try:
    GENAI_KEY = st.secrets["GEMINI_API_KEY"]
except:
    GENAI_KEY = "66ad043d6024749fa4bf92f0a6782397" # Lấy tại https://aistudio.google.com/

genai.configure(api_key=GENAI_KEY)
# =========================
# DANH MỤC VẬT TƯ
# =========================

FARM_RESOURCES = {

    "Dinh dưỡng": {
        "Hữu cơ (Ưu tiên)": "Phân gà oai, Đạm cá, Humic Acid, Dịch chuối, Phân trùn quế.",
        "Vô cơ (Bổ sung)": "NPK 20-20-15, Kali Sunfat."
    },

    "Trị bệnh": {
        "Sinh học (Ưu tiên)": "Trichoderma, Nano Bạc, Tinh dầu thảo mộc, Bordeaux.",
        "Hóa học (Khi bệnh nặng)": "Metalaxyl, Validamycin."
    },

    "Trị côn trùng": {
        "Sinh học (Ưu tiên)": "BT, Dịch tỏi ớt, Nấm xanh Metarhizium.",
        "Hóa học (Khi bùng dịch)": "Abamectin."
    }

}


# =========================
# TRI THỨC CÂY TRỒNG
# =========================

CROP_KNOWLEDGE = {

    "Ớt Aji Charapita": [

        {
            "stage": "Cây con",
            "days": (0,20),

            "organic": "Tưới Humic + Trichoderma để kích rễ.",

            "backup": "Nếu cây héo rũ, dùng Metalaxyl tưới gốc.",

            "note": "Phủ gốc bằng xơ dừa để giữ ẩm."
        },

        {
            "stage": "Phát triển lá",
            "days": (21,60),

            "organic": "Phun đạm cá + dịch tỏi ớt ngừa sâu.",

            "backup": "Nếu bọ trĩ bùng phát, dùng Abamectin liều nhẹ.",

            "note": "Bấm ngọn để cây phân cành."
        },

        {
            "stage": "Ra hoa / Trái",
            "days": (61,150),

            "organic": "Bón phân trùn quế + dịch chuối.",

            "backup": "Nếu rụng hoa, bổ sung Canxi-Bo.",

            "note": "Không tưới đẫm buổi tối."
        }

    ],

    # BỔ SUNG PHÁC ĐỒ CHUNG
    "Chung": [

        {
            "stage": "Cây non",
            "days": (0,30),

            "organic": "Tưới Humic + Trichoderma kích rễ.",

            "backup": "Nếu héo rũ dùng Metalaxyl nhẹ.",

            "note": "Giữ ẩm đất, tránh nắng gắt."
        },

        {
            "stage": "Sinh trưởng",
            "days": (31,90),

            "organic": "Bón phân hữu cơ hoai + đạm cá.",

            "backup": "Nếu sâu ăn lá dùng BT.",

            "note": "Theo dõi côn trùng định kỳ."
        },

        {
            "stage": "Ra hoa / kết trái",
            "days": (91,200),

            "organic": "Bổ sung Kali + dịch chuối.",

            "backup": "Nếu rụng hoa bổ sung Canxi-Bo.",

            "note": "Không tưới quá nhiều nước."
        }

    ]

}


# =========================
# AI CẢNH BÁO
# =========================

def ai_crop_warning(stage, weather):

    if not weather:
        return None

    temp = weather["temp"]
    hum = weather["hum"]
    rain = weather["rain"]

    if hum > 85:
        return "🦠 Độ ẩm cao → nguy cơ nấm bệnh. Khuyến nghị: Trichoderma hoặc Nano Bạc."
    if temp > 32 and hum < 50:
        return "🌵 Trời nóng khô → Nguy cơ bùng phát Bọ trĩ & Nhện đỏ. Khuyến nghị: Phun nước mát lên lá và dùng dịch tỏi ớt."
    if temp > 34:
        return "🔥 Nhiệt độ cao → cây dễ sốc nhiệt. Nên tăng tưới và che nắng."
    if stage == "Phát triển lá" and rain > 0:
        return "🐛 Sau mưa cây ra chồi non → Dễ bị sâu khoang, sâu xanh tấn công. Hãy kiểm tra mặt dưới lá."
    if rain > 5:
        return "🌧 Mưa nhiều → nguy cơ thối rễ. Nên rải vôi và kiểm tra thoát nước."

    if stage == "Ra hoa / Trái" and hum > 80:
        return "⚠ Giai đoạn ra hoa gặp ẩm cao → dễ rụng hoa."

    return None


# =========================
# TÍNH VPD
# =========================

def calculate_vpd(temp, humidity):

    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)

    return svp - avp


# =========================
# LẤY THỜI TIẾT (CACHE)
# =========================

@st.cache_data(ttl=600)
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
# STREAMLIT CONFIG
# =========================

st.set_page_config(
    page_title="Aji Farm Pro",
    layout="wide",
    page_icon="🌶️"
)

data = load_data()

weather = get_real_weather()


# =========================
# SIDEBAR
# =========================

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


# =========================
# DASHBOARD
# =========================

if menu == "📊 Dashboard Chuyên sâu":

    st.title("📊 Quan trắc VPD & Thời tiết")

    if weather:

        c1,c2,c3,c4 = st.columns(4)

        c1.metric("Nhiệt độ", f"{weather['temp']}°C")
        c2.metric("Độ ẩm", f"{weather['hum']}%")
        c3.metric("Mưa", f"{weather['rain']}mm")
        c4.metric("Thời tiết", weather['desc'].capitalize())

        vpd = calculate_vpd(weather['temp'], weather['hum'])

        st.markdown(f"### Chỉ số VPD: `{vpd:.2f} kPa`")

        if vpd < 0.5:
            st.error("Nguy cơ nấm bệnh cao")

        elif vpd > 2:
            st.warning("Không khí khô")

        else:
            st.success("Điều kiện sinh trưởng tốt")

    else:

        st.error("Không lấy được dữ liệu thời tiết")


# =========================
# QUẢN LÝ CÂY
# =========================

elif menu == "🌱 Quản lý Cây trồng":

    st.title("🌱 Quản lý Vườn")

    with st.expander("➕ Thêm cây mới"):

        name = st.text_input("Tên cây")

        crop_type = st.selectbox(
            "Loại cây",
            list(CROP_KNOWLEDGE.keys()) + ["Khác"]
        )

        date = st.date_input("Ngày trồng")

        if st.button("Xác nhận lưu"):

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

    if plants:

        for p in plants:

            with st.container(border=True):

                col_info,col_ai,col_action = st.columns([1,2,1])

                with col_info:

                    st.subheader(f"🌿 {p['name']}")

                    # CHẶN TUỔI CÂY ÂM
                    age = max(0, (datetime.now() - datetime.strptime(p['date'], "%Y-%m-%d")).days)

                    st.write(f"Tuổi cây: {age} ngày")


                with col_ai:

                    st.markdown("#### 🌿 Phác đồ chăm sóc Thuận tự nhiên")

                    # FALLBACK PHÁC ĐỒ CHUNG
                    k_key = next((k for k in CROP_KNOWLEDGE.keys() if k in p['name']), "Chung")

                    if k_key:

                        stages = CROP_KNOWLEDGE[k_key]

                        curr = next(
                            (s for s in stages if s['days'][0] <= age <= s['days'][1]),
                            stages[-1]
                        )

                        st.info(f"📍 Giai đoạn: {curr['stage']}")

                        tab_org, tab_chem = st.tabs(
                            ["🍃 Phương án Hữu cơ", "🧪 Phương án Dự phòng"]
                        )

                        with tab_org:

                            st.success(curr["organic"])

                            st.caption(
                                f"Vật tư gợi ý: {FARM_RESOURCES['Dinh dưỡng']['Hữu cơ (Ưu tiên)']}"
                            )

                        with tab_chem:

                            st.warning(curr["backup"])

                        st.caption(f"📌 {curr['note']}")

                        warning = ai_crop_warning(curr["stage"], weather)

                        if warning:
                            st.error(f"🤖 AI Cảnh báo: {warning}")

                    else:

                        st.info("Đang cập nhật phác đồ chăm sóc...")


                    if weather:

                        st.markdown("#### 🌦 Điều chỉnh theo thời tiết")

                        if weather["temp"] > 32:

                            st.warning("Trời nóng: tăng lượng nước tưới")

                        if weather["hum"] > 85:

                            st.error(
                                f"Độ ẩm cao → nguy cơ nấm. Gợi ý: {FARM_RESOURCES['Trị bệnh']['Sinh học (Ưu tiên)']}"
                            )

                        if weather["rain"] > 0:

                            st.info("Sau mưa: rải vôi quanh gốc")


                with col_action:

                    if st.button("Xóa", key=f"del_{p['id']}"):

                        data = delete_plant(data, p["id"])
                        st.rerun()

    else:

        st.info("Chưa có cây trồng")


# =========================
# AI ASSISTANT
# =========================

elif menu == "💬 AI Assistant":

    st.title("💬 Trợ lý Nông nghiệp")

    plant_count = len(data.get("plants", []))

    st.info(f"🌱 Hệ thống đang theo dõi {plant_count} cây trồng.")

    for chat in data.get("chat_history", []):

        with st.chat_message("user"):
            st.write(chat["user"])

        with st.chat_message("assistant"):
            st.write(chat["ai"])


    if prompt := st.chat_input("Hỏi về cây trồng..."):

        with st.chat_message("user"):
            st.write(prompt)

        if weather:

            ai_res = f"Nhiệt độ hiện tại {weather['temp']}°C. "

            if weather["temp"] > 30:
                ai_res += "Trời khá nóng, nên chú ý tưới nước."

            elif weather["hum"] > 85:
                ai_res += "Độ ẩm cao, nên phòng nấm bệnh."

            else:
                ai_res += "Thời tiết thuận lợi cho cây."

        else:

            ai_res = "Chưa lấy được dữ liệu thời tiết."

        data = add_chat(data, prompt, ai_res)

        with st.chat_message("assistant"):
            st.write(ai_res)
