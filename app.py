import streamlit as st
import requests
import math
from datetime import datetime
from database import load_data, save_data, add_plant, delete_plant, add_chat, add_log

st.set_page_config(page_title="AI Smart Farm", layout="wide")

CITY = "Hue"

# Lấy API KEY từ secrets (an toàn)
try:
    API_KEY = st.secrets["OPENWEATHER_API_KEY"]
except:
    API_KEY = "YOUR_OPENWEATHER_API_KEY"


@st.cache_data(ttl=600)
def get_real_weather():
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric&lang=vi"
        r = requests.get(url, timeout=10)
        d = r.json()

        if "main" not in d:
            return None

        return {
            "temp": d["main"]["temp"],
            "hum": d["main"]["humidity"],
            "rain": d.get("rain", {}).get("1h", 0),
            "desc": d["weather"][0]["description"]
        }
    except:
        return None


def calc_vpd(temp, humidity):
    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)
    return round(svp - avp, 2)


CROP_KNOWLEDGE = {

    "Ớt": [
        {
            "stage": "Cây con",
            "days": (0, 20),
            "organic": "Dịch chuối + đạm cá",
            "chemical": "NPK 20-20-15"
        },
        {
            "stage": "Sinh trưởng",
            "days": (21, 50),
            "organic": "Đạm cá + humic",
            "chemical": "NPK 16-16-8"
        },
        {
            "stage": "Ra hoa",
            "days": (51, 80),
            "organic": "Chuối + canxi",
            "chemical": "NPK 15-5-20"
        }
    ],

    "Cà chua": [
        {
            "stage": "Cây con",
            "days": (0, 20),
            "organic": "Humic + rong biển",
            "chemical": "NPK 20-20-15"
        },
        {
            "stage": "Sinh trưởng",
            "days": (21, 45),
            "organic": "Đạm cá",
            "chemical": "NPK 16-16-8"
        },
        {
            "stage": "Ra hoa",
            "days": (46, 80),
            "organic": "Chuối + canxi",
            "chemical": "NPK 15-5-20"
        }
    ],

    "Chung": [
        {
            "stage": "Sinh trưởng",
            "days": (0, 999),
            "organic": "Phân hữu cơ hoai mục",
            "chemical": "NPK cân đối"
        }
    ]
}


data = load_data()

menu = st.sidebar.radio(
    "Menu",
    [
        "📊 Dashboard",
        "🌱 Quản lý Cây trồng",
        "💬 Trợ lý AI Assistant"
    ]
)

weather = get_real_weather()

# ================= DASHBOARD =================

if menu == "📊 Dashboard":

    st.title("📊 Bảng điều khiển Nông trại")

    if weather:

        temp = weather["temp"]
        hum = weather["hum"]
        rain = weather["rain"]

        vpd = calc_vpd(temp, hum)

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("🌡 Nhiệt độ", f"{temp} °C")
        c2.metric("💧 Độ ẩm", f"{hum} %")
        c3.metric("🌧 Lượng mưa", f"{rain} mm")
        c4.metric("VPD", vpd)

        st.caption(weather["desc"])

        if vpd < 0.5:
            st.warning("VPD thấp → môi trường ẩm, nguy cơ nấm bệnh")

        if vpd > 2:
            st.warning("VPD cao → cây thoát hơi nước mạnh, dễ khô hạn")

    else:
        st.error("Không lấy được dữ liệu thời tiết")


# ================= QUẢN LÝ CÂY =================

elif menu == "🌱 Quản lý Cây trồng":

    st.title("🌱 Quản lý Cây trồng")

    with st.form("addplant"):

        name = st.text_input("Tên cây")
        date = st.date_input("Ngày trồng")

        submitted = st.form_submit_button("Thêm cây")

        if submitted and name:
            data = add_plant(data, name, date.strftime("%Y-%m-%d"))
            st.success("Đã thêm cây")
            st.rerun()

    plants = data.get("plants", [])

    if plants:

        for p in plants:

            with st.container(border=True):

                col_info, col_ai, col_action = st.columns([1, 2, 1])

                with col_info:

                    st.subheader(f"🌿 {p['name']}")

                    age = max(
                        0,
                        (datetime.now() - datetime.strptime(p["date"], "%Y-%m-%d")).days
                    )

                    st.write(f"Tuổi cây: **{age} ngày**")
                    st.caption(f"Ngày trồng: {p['date']}")

                with col_ai:

                    k_key = next(
                        (k for k in CROP_KNOWLEDGE if k in p["name"]),
                        "Chung"
                    )

                    stages = CROP_KNOWLEDGE[k_key]

                    curr = next(
                        (s for s in stages if s["days"][0] <= age <= s["days"][1]),
                        stages[-1]
                    )

                    st.info(f"Giai đoạn: {curr['stage']}")

                    tab1, tab2 = st.tabs(["Hữu cơ", "Dự phòng"])

                    with tab1:
                        st.write(curr["organic"])

                    with tab2:
                        st.write(curr["chemical"])

                    if weather:

                        if weather["hum"] > 85:
                            st.warning("Độ ẩm cao → nguy cơ nấm bệnh")

                        if weather["temp"] > 34:
                            st.warning("Nhiệt độ cao → cây dễ sốc nhiệt")

                        if weather["rain"] > 5:
                            st.warning("Mưa nhiều → nguy cơ thối rễ")

                with col_action:

                    with st.popover("📝 Chỉnh sửa"):

                        new_name = st.text_input(
                            "Tên mới",
                            value=p["name"],
                            key=f"name_{p['id']}"
                        )

                        new_date = st.date_input(
                            "Ngày trồng mới",
                            value=datetime.strptime(p["date"], "%Y-%m-%d"),
                            key=f"date_{p['id']}"
                        )

                        if st.button("Cập nhật", key=f"update_{p['id']}"):

                            p["name"] = new_name
                            p["date"] = new_date.strftime("%Y-%m-%d")

                            save_data(data)

                            st.success("Đã cập nhật thông tin")
                            st.rerun()

                    if st.button("🗑️ Xóa cây", key=f"del_{p['id']}"):
                        data = delete_plant(data, p["id"])
                        st.rerun()

                with st.expander("📖 Nhật ký chăm sóc"):

                    c_type, c_content, c_btn = st.columns([1, 2, 1])

                    with c_type:
                        action = st.selectbox(
                            "Loại",
                            ["Bón phân", "Phun thuốc"],
                            key=f"log_type_{p['id']}"
                        )

                    with c_content:
                        note = st.text_input(
                            "Nội dung",
                            key=f"log_note_{p['id']}"
                        )

                    with c_btn:
                        st.write("")
                        if st.button("Ghi sổ", key=f"btn_log_{p['id']}"):

                            if note:
                                data = add_log(data, p["id"], action, note)
                                st.success("Đã lưu nhật ký")
                                st.rerun()

                    st.divider()

                    logs = p.get("logs", [])

                    if logs:

                        for l in logs[:5]:

                            color = "blue" if l["type"] == "Bón phân" else "orange"

                            st.markdown(
                                f"**{l['date']}** | :{color}[{l['type']}] | {l['content']}"
                            )

                    else:
                        st.caption("Chưa có nhật ký chăm sóc")


# ================= AI ASSISTANT =================

elif menu == "💬 Trợ lý AI Assistant":

    st.title("💬 Trợ lý AI Nông nghiệp")

    st.info(
        f"Hệ thống đang theo dõi {len(data.get('plants', []))} cây trồng."
    )

    history = data.get("chat", [])

    for h in history:

        with st.chat_message("user"):
            st.write(h["q"])

        with st.chat_message("assistant"):
            st.write(h["a"])

    if prompt := st.chat_input("Hỏi về tình trạng cây trồng..."):

        weather = get_real_weather()

        if weather:

            vpd = calc_vpd(weather["temp"], weather["hum"])

            ai_res = (
                f"Hiện tại ở {CITY}: "
                f"{weather['temp']}°C, "
                f"độ ẩm {weather['hum']}%, "
                f"mưa {weather['rain']} mm."
            )

            if vpd < 0.5:
                ai_res += f" ⚠️ VPD thấp ({vpd}) → nguy cơ nấm bệnh."

            elif vpd > 2:
                ai_res += f" ⚠️ VPD cao ({vpd}) → cây dễ mất nước."

            else:
                ai_res += f" VPD {vpd} → điều kiện môi trường ổn định."

        else:
            ai_res = "Không lấy được dữ liệu thời tiết."

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            st.write(ai_res)

        data = add_chat(data, prompt, ai_res)
        st.rerun()
