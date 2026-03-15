import streamlit as st
import requests
import math
from datetime import datetime
from database import load_data, add_plant, delete_plant, add_chat, save_data

# =========================
# CẤU HÌNH
# =========================

API_KEY = "YOUR_OPENWEATHER_API_KEY"
LAT, LON = 16.4637, 107.5909


# =========================
# TRI THỨC CÂY TRỒNG
# =========================

CROP_KNOWLEDGE = {

    "Ớt Aji Charapita": [

        {
            "stage": "Cây con",
            "days": (0,20),
            "organic": "Humic + Trichoderma kích rễ",
            "backup": "Nếu héo rũ: Metalaxyl tưới gốc",
            "note": "Giữ ẩm nhẹ đất"
        },

        {
            "stage": "Phát triển",
            "days": (21,60),
            "organic": "Đạm cá + dịch tỏi ớt",
            "backup": "Bọ trĩ nặng dùng Abamectin",
            "note": "Tỉa nhánh yếu"
        },

        {
            "stage": "Ra hoa / Trái",
            "days": (61,150),
            "organic": "Phân trùn + dịch chuối",
            "backup": "Rụng hoa → Canxi Bo",
            "note": "Không tưới đẫm ban đêm"
        }

    ],

    "Chung": [

        {
            "stage": "Cây non",
            "days": (0,30),
            "organic": "Humic + Trichoderma",
            "backup": "Metalaxyl nếu thối rễ",
            "note": "Giữ ẩm đất"
        },

        {
            "stage": "Sinh trưởng",
            "days": (31,90),
            "organic": "Phân hữu cơ + đạm cá",
            "backup": "BT nếu sâu ăn lá",
            "note": "Theo dõi sâu bệnh"
        },

        {
            "stage": "Ra hoa",
            "days": (91,200),
            "organic": "Kali + dịch chuối",
            "backup": "Canxi Bo chống rụng hoa",
            "note": "Không tưới quá nhiều"
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
        return "🦠 Độ ẩm cao → nguy cơ nấm."

    if temp > 34:
        return "🔥 Nhiệt độ cao → cây dễ sốc."

    if rain > 5:
        return "🌧 Mưa nhiều → nguy cơ thối rễ."

    if stage == "Ra hoa / Trái" and hum > 80:
        return "⚠ Ẩm cao khi ra hoa → dễ rụng hoa."

    return None


# =========================
# VPD
# =========================

def calculate_vpd(temp, humidity):

    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)

    return svp - avp


# =========================
# WEATHER API
# =========================

@st.cache_data(ttl=600)
def get_real_weather():

    url = f"http://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric&lang=vi"

    try:

        res = requests.get(url)

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
# CONFIG APP
# =========================

st.set_page_config(
    page_title="Aji Farm AI",
    layout="wide"
)

data = load_data()
weather = get_real_weather()


# =========================
# SIDEBAR
# =========================

with st.sidebar:

    st.title("🌶 Aji Farm AI")

    menu = st.radio(
        "Menu",
        [
            "📊 Dashboard",
            "🌱 Quản lý Cây trồng",
            "💬 AI Assistant"
        ]
    )


# =========================
# DASHBOARD
# =========================

if menu == "📊 Dashboard":

    st.title("📊 Quan trắc môi trường")

    if weather:

        c1,c2,c3,c4 = st.columns(4)

        c1.metric("Nhiệt độ", f"{weather['temp']}°C")
        c2.metric("Độ ẩm", f"{weather['hum']}%")
        c3.metric("Mưa", f"{weather['rain']}mm")
        c4.metric("Thời tiết", weather["desc"])

        vpd = calculate_vpd(weather["temp"], weather["hum"])

        st.markdown(f"### VPD: `{vpd:.2f} kPa`")

        if vpd < 0.5:
            st.error("Nguy cơ nấm cao")

        elif vpd > 2:
            st.warning("Không khí khô")

        else:
            st.success("Điều kiện tốt")


# =========================
# QUẢN LÝ CÂY
# =========================

elif menu == "🌱 Quản lý Cây trồng":

    st.title("🌱 Quản lý vườn")

    with st.expander("➕ Thêm cây"):

        name = st.text_input("Tên cây")

        crop_type = st.selectbox(
            "Loại cây",
            list(CROP_KNOWLEDGE.keys()) + ["Khác"]
        )

        date = st.date_input("Ngày trồng")

        if st.button("Lưu"):

            if name.strip() != "":

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

                col_info, col_ai, col_action = st.columns([1,2,1])


                # INFO
                with col_info:

                    st.subheader(f"🌿 {p['name']}")

                    age = max(
                        0,
                        (datetime.now() - datetime.strptime(p['date'],"%Y-%m-%d")).days
                    )

                    st.write(f"Tuổi cây: **{age} ngày**")
                    st.caption(f"Ngày trồng: {p['date']}")


                # AI + PHÁC ĐỒ
                with col_ai:

                    k_key = next((k for k in CROP_KNOWLEDGE if k in p["name"]),"Chung")

                    stages = CROP_KNOWLEDGE[k_key]

                    curr = next(
                        (s for s in stages if s["days"][0] <= age <= s["days"][1]),
                        stages[-1]
                    )

                    st.info(f"Giai đoạn: {curr['stage']}")

                    tab1,tab2 = st.tabs(["Hữu cơ","Dự phòng"])

                    with tab1:
                        st.success(curr["organic"])

                    with tab2:
                        st.warning(curr["backup"])

                    st.caption(curr["note"])

                    warn = ai_crop_warning(curr["stage"],weather)

                    if warn:
                        st.error(warn)


                    # --- NHẬT KÝ CHĂM SÓC ---
                    with st.expander("📖 Nhật ký chăm sóc"):

                        c_type,c_content,c_btn = st.columns([1,2,1])

                        with c_type:

                            action = st.selectbox(
                                "Loại",
                                ["Bón phân","Phun thuốc"],
                                key=f"log_type_{p['id']}"
                            )

                        with c_content:

                            note = st.text_input(
                                "Nội dung",
                                key=f"log_note_{p['id']}"
                            )

                        with c_btn:

                            st.write(" ")

                            if st.button("Ghi sổ",key=f"log_btn_{p['id']}"):

                                if note:

                                    from database import add_log

                                    data = add_log(
                                        data,
                                        p["id"],
                                        action,
                                        note
                                    )

                                    st.success("Đã lưu")
                                    st.rerun()

                        st.divider()

                        logs = p.get("logs",[])

                        if logs:

                            for l in logs[:5]:

                                color = "blue" if l["type"]=="Bón phân" else "orange"

                                st.markdown(
                                    f"**{l['date']}** | :{color}[{l['type']}] | {l['content']}"
                                )

                        else:

                            st.caption("Chưa có nhật ký.")


                # ACTION
                with col_action:

                    with st.popover("📝 Chỉnh sửa"):

                        new_name = st.text_input(
                            "Tên mới",
                            value=p["name"],
                            key=f"edit_{p['id']}"
                        )

                        new_date = st.date_input(
                            "Ngày trồng",
                            value=datetime.strptime(p["date"],"%Y-%m-%d"),
                            key=f"date_{p['id']}"
                        )

                        if st.button("Cập nhật",key=f"update_{p['id']}"):

                            p["name"] = new_name
                            p["date"] = new_date.strftime("%Y-%m-%d")

                            save_data(data)

                            st.success("Đã cập nhật")
                            st.rerun()


                    if st.button("🗑 Xóa",key=f"del1_{p['id']}"):

                        st.session_state[f"confirm_{p['id']}"] = True


                    if st.session_state.get(f"confirm_{p['id']}",False):

                        st.error("Bạn chắc chắn?")

                        c1,c2 = st.columns(2)

                        with c1:

                            if st.button("Xác nhận",key=f"del2_{p['id']}"):

                                data = delete_plant(data,p["id"])

                                del st.session_state[f"confirm_{p['id']}"]

                                st.rerun()

                        with c2:

                            if st.button("Hủy",key=f"cancel_{p['id']}"):

                                del st.session_state[f"confirm_{p['id']}"]

                                st.rerun()


# =========================
# AI ASSISTANT
# =========================

elif menu == "💬 AI Assistant":

    st.title("💬 Trợ lý nông nghiệp")

    for chat in data.get("chat_history",[]):

        with st.chat_message("user"):
            st.write(chat["user"])

        with st.chat_message("assistant"):
            st.write(chat["ai"])


    if prompt := st.chat_input("Hỏi về cây..."):

        if weather:

            ai_res = f"Nhiệt độ {weather['temp']}°C. "

            if weather["hum"] > 85:
                ai_res += "Độ ẩm cao, nên phòng nấm."

            elif weather["temp"] > 32:
                ai_res += "Trời nóng, nên tưới thêm."

            else:
                ai_res += "Thời tiết khá tốt."

        else:

            ai_res = "Không lấy được dữ liệu thời tiết."

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            st.write(ai_res)

        data = add_chat(data,prompt,ai_res)

