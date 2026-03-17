"""
app.py - GREEN FARM
────────────────────────────────────────────────────────────
Ứng dụng quản lý vườn thông minh với AI (Gemini).
Các module phụ thuộc: database.py, weather.py

Chạy: streamlit run app.py
"""

import io
import math
import re
import requests
import streamlit as st
import google.generativeai as genai
from PIL import Image
from datetime import datetime
from database import (
    load_data, save_data, add_plant,
    delete_plant, add_chat, get_crop_history,
    archive_and_delete_plant
)
from streamlit_js_eval import get_geolocation
from weather import get_weather, get_city_name

# =============================================================
# CẤU HÌNH GEMINI
# =============================================================

try:
    GENAI_KEY    = st.secrets["GEMINI_API_KEY"]
    GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")
except (KeyError, FileNotFoundError):
    GENAI_KEY    = ""
    GEMINI_MODEL = "gemini-1.5-flash"

genai.configure(api_key=GENAI_KEY)


@st.cache_resource
def get_gemini_model(model_name: str):
    """Khởi tạo Gemini model 1 lần duy nhất, tái sử dụng mọi nơi."""
    return genai.GenerativeModel(model_name)


model = get_gemini_model(GEMINI_MODEL)

# =============================================================
# DANH MỤC VẬT TƯ
# =============================================================

FARM_RESOURCES = {
    "Dinh dưỡng": {
        "Hữu cơ (Ưu tiên)": "Phân gà hoai, Đạm cá, Humic Acid, Dịch chuối, Phân trùn quế...",
        "Vô cơ (Bổ sung)":  "NPK 20-20-15, Kali Sunfat..."
    },
    "Trị bệnh": {
        "Sinh học (Ưu tiên)":      "Trichoderma, Nano Bạc, Tinh dầu thảo mộc, Bordeaux...",
        "Hóa học (Khi bệnh nặng)": "Metalaxyl, Validamycin..."
    },
    "Trị côn trùng": {
        "Sinh học (Ưu tiên)":      "BT, Dịch tỏi ớt, Nấm xanh Metarhizium...",
        "Hóa học (Khi bùng dịch)": "Abamectin."
    }
}

# =============================================================
# TRI THỨC CÂY TRỒNG
# =============================================================

CROP_KNOWLEDGE = {
    "Ớt Aji Charapita": [
        {"stage": "Cây con",       "days": (0, 20),
         "organic": "Tưới Humic + Trichoderma để kích rễ.",
         "backup":  "Nếu cây héo rũ, dùng Metalaxyl tưới gốc.",
         "note":    "Phủ gốc bằng xơ dừa để giữ ẩm."},
        {"stage": "Phát triển lá", "days": (21, 60),
         "organic": "Phun đạm cá + dịch tỏi ớt ngừa sâu.",
         "backup":  "Nếu bọ trĩ bùng phát, dùng Abamectin liều nhẹ.",
         "note":    "Bấm ngọn để cây phân cành."},
        {"stage": "Ra hoa / Trái", "days": (61, 150),
         "organic": "Bón phân trùn quế + dịch chuối.",
         "backup":  "Nếu rụng hoa, bổ sung Canxi-Bo.",
         "note":    "Không tưới đẫm buổi tối."}
    ],
    "Chung": [
        {"stage": "Cây non",           "days": (0, 30),
         "organic": "Tưới Humic + Trichoderma kích rễ.",
         "backup":  "Nếu héo rũ dùng Metalaxyl nhẹ.",
         "note":    "Giữ ẩm đất, tránh nắng gắt."},
        {"stage": "Sinh trưởng",       "days": (31, 90),
         "organic": "Bón phân hữu cơ hoai + đạm cá.",
         "backup":  "Nếu sâu ăn lá dùng BT.",
         "note":    "Theo dõi côn trùng định kỳ."},
        {"stage": "Ra hoa / kết trái", "days": (91, 200),
         "organic": "Bổ sung Kali + dịch chuối.",
         "backup":  "Nếu rụng hoa bổ sung Canxi-Bo.",
         "note":    "Không tưới quá nhiều nước."}
    ]
}

# =============================================================
# DANH SÁCH CÂY TRỒNG
# =============================================================

CROP_LIST = [
    "Ớt Aji Charapita", "Ớt Chỉ thiên", "Ớt Xiêm",
    "Bầu", "Mai vàng", "Cà chua Beef", "Dưa leo",
    "Chanh", "Cà tím", "Bắp cải", "Xà lách",
    "Rau muống", "Húng quế", "Cần tây", "Khác"
]

# =============================================================
# HELPER FUNCTIONS
# =============================================================

def calculate_vpd(temp: float, humidity: float) -> float:
    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    avp = svp * (humidity / 100)
    return round(svp - avp, 3)


def safe_weather_str(w: dict) -> str:
    if not w or w.get("temp") is None:
        return "N/A"
    return f"{w.get('temp','?')}°C, {w.get('hum','?')}% ẩm"


def build_season_context(history: list) -> str:
    if not history:
        return "Chưa có dữ liệu vụ trước."
    lines = []
    for i, s in enumerate(history[-3:], 1):
        lines.append(
            f"--- Vụ {i} ({s.get('date_start','')}"
            f" → {s.get('date_end','')}) ---"
        )
        logs = s.get("logs", [])
        if logs:
            log_texts = [
                f"{l.get('d', l.get('date',''))}: {l.get('c', l.get('content',''))}"
                for l in logs[-10:]
            ]
            lines.append("Nhật ký: " + " | ".join(log_texts))
        recipe = s.get("recipe", "")
        if recipe:
            lines.append(f"Quy trình AI vụ đó: {recipe[:300]}...")
    return "\n".join(lines)


def get_weather_safe() -> dict:
    """Trả về dict weather mặc định, không bao giờ None."""
    return {
        "temp": None, "hum": None, "wind": None,
        "rain": None, "desc": "Đang tải...",
        "city": "Đang xác định vị trí...",
        "lat":  DEFAULT_LAT, "lon": DEFAULT_LON,
        "agri_warnings": []
    }

# =============================================================
# STREAMLIT CONFIG
# =============================================================

st.set_page_config(page_title="GREEN FARM", layout="wide", page_icon="🌿")

# =============================================================
# XÁC THỰC NGƯỜI DÙNG
# =============================================================

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🌿 GREEN FARM")
        st.markdown("### 🔐 Đăng nhập")
        password = st.text_input("Nhập mật khẩu:", type="password", key="login_pw")
        if st.button("Đăng nhập"):
            try:
                correct_pw = st.secrets["APP_PASSWORD"]
            except (KeyError, FileNotFoundError):
                correct_pw = "greenfarm2024"
            if password == correct_pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Mật khẩu không đúng!")
        st.stop()


check_password()

# =============================================================
# GPS — chỉ gọi khi chưa có tọa độ
# =============================================================

DEFAULT_LAT, DEFAULT_LON = 16.4637, 107.5909

if "gps_lat" not in st.session_state:
    st.session_state["gps_lat"] = None
    st.session_state["gps_lon"] = None

if st.session_state["gps_lat"] is None:
    with st.spinner("📍 Đang xác định vị trí... (Vui lòng cho phép truy cập vị trí)"):
        loc = get_geolocation()
    if loc and isinstance(loc, dict) and "coords" in loc:
        try:
            st.session_state["gps_lat"] = float(loc["coords"]["latitude"])
            st.session_state["gps_lon"] = float(loc["coords"]["longitude"])
        except (KeyError, ValueError, TypeError):
            st.session_state["gps_lat"] = DEFAULT_LAT
            st.session_state["gps_lon"] = DEFAULT_LON
    else:
        st.session_state["gps_lat"] = DEFAULT_LAT
        st.session_state["gps_lon"] = DEFAULT_LON

# =============================================================
# THỜI TIẾT (cache tầng 2)
# =============================================================

@st.cache_data(ttl=600)
def fetch_weather_data(lat: float, lon: float) -> dict:
    return get_weather(lat=lat, lon=lon)


@st.cache_data(ttl=600)
def fetch_meteo_weather(lat: float, lon: float) -> dict:
    WMO_DESCRIPTIONS = {
        0: "Trời quang",    1: "Ít mây",          2: "Mây rải rác",
        3: "Nhiều mây",    45: "Sương mù",        48: "Sương mù có băng",
        51: "Mưa phùn nhẹ", 53: "Mưa phùn",      55: "Mưa phùn dày",
        61: "Mưa nhỏ",     63: "Mưa vừa",         65: "Mưa to",
        80: "Mưa rào nhẹ", 81: "Mưa rào",         82: "Mưa rào nặng",
        95: "Dông bão",    96: "Dông có mưa đá",  99: "Dông mưa đá lớn",
    }
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
        f"&timezone=auto"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        curr = res.json().get("current", {})
        code = curr.get("weather_code", -1)
        return {
            "temp": curr.get("temperature_2m"),
            "hum":  curr.get("relative_humidity_2m"),
            "desc": WMO_DESCRIPTIONS.get(code, "Không xác định"),
            "code": code,
        }
    except requests.exceptions.Timeout:
        st.warning("Không thể lấy dữ liệu thời tiết (timeout).")
    except requests.exceptions.RequestException as e:
        st.warning(f"Lỗi kết nối thời tiết: {e}")
    except (KeyError, ValueError):
        st.warning("Dữ liệu thời tiết không hợp lệ.")
    return {"temp": 28, "hum": 75, "desc": "N/A", "code": -1}


# =============================================================
# TẢI DỮ LIỆU
# =============================================================

data = load_data()

lat      = st.session_state.get("gps_lat") or DEFAULT_LAT
lon      = st.session_state.get("gps_lon") or DEFAULT_LON
_weather = fetch_weather_data(lat, lon)
weather  = _weather if _weather is not None else get_weather_safe()

# =============================================================
# SIDEBAR
# =============================================================

with st.sidebar:
    st.title("🌿 GREEN FARM")
    city_display = weather.get("city", "Đang xác định...")
    st.caption(f"📍 {city_display}")

    menu_options = [
        "📊 Dashboard Chuyên sâu",
        "🌱 Quản lý Cây trồng",
        "📸 Camera Chẩn đoán",
        "💬 AI Assistant"
    ]

    default_idx = 0
    if ("menu_choice" in st.session_state
            and st.session_state["menu_choice"] in menu_options):
        default_idx = menu_options.index(st.session_state["menu_choice"])

    menu = st.radio("Menu", menu_options, index=default_idx, key="menu_radio")

    if "current_menu" not in st.session_state:
        st.session_state["current_menu"] = menu
    if st.session_state["current_menu"] != menu:
        st.session_state["prev_menu"]    = st.session_state["current_menu"]
        st.session_state["current_menu"] = menu
    st.session_state["menu_choice"] = menu

# =============================================================
# HELPER: NÚT BACK
# =============================================================

def back_button():
    if "prev_menu" in st.session_state:
        if st.button("⬅️ Quay lại"):
            st.session_state["menu_choice"] = st.session_state["prev_menu"]
            st.rerun()

# =============================================================
# 📊 DASHBOARD
# =============================================================

if menu == "📊 Dashboard Chuyên sâu":
    back_button()
    st.title("📊 Quan trắc VPD & Thời tiết")

    city = weather.get("city", "Đang xác định...")
    st.markdown(f"📍 **{city}**")

    if weather.get("temp") is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Nhiệt độ",  f"{weather['temp']}°C")
        c2.metric("Độ ẩm",     f"{weather['hum']}%")
        c3.metric("Mưa",       f"{weather['rain']}mm")
        c4.metric("Thời tiết", weather["desc"].capitalize())

        if weather.get("wind") is not None:
            wind_val   = weather["wind"]
            wind_label = (
                "⛔ Rất mạnh" if wind_val >= 40
                else "⚠️ Vừa"  if wind_val >= 20
                else "✅ Nhẹ"
            )
            st.metric("💨 Gió", f"{wind_val} km/h", wind_label)

        vpd = calculate_vpd(weather["temp"], weather["hum"])
        st.markdown(f"### Chỉ số VPD: `{vpd:.2f} kPa`")
        if vpd < 0.5:
            st.error("🦠 Nguy cơ nấm bệnh cao (VPD quá thấp)")
        elif vpd > 2.0:
            st.warning("🌵 Không khí quá khô (VPD cao)")
        else:
            st.success("✅ Điều kiện sinh trưởng tốt")

        warnings = weather.get("agri_warnings", [])
        if warnings:
            st.markdown("### 🚨 Cảnh báo Nông nghiệp")
            for w in warnings:
                st.info(w)
    else:
        st.info("⏳ Đang tải dữ liệu thời tiết, vui lòng chờ...")

# =============================================================
# 🌱 QUẢN LÝ CÂY TRỒNG
# =============================================================

elif menu == "🌱 Quản lý Cây trồng":
    back_button()
    st.title("🌱 Quản lý Vườn & Hệ thống Tối ưu AI")

    with st.expander("⚙️ Thiết lập & Quản lý danh sách cây", expanded=False):
        tab_add, tab_edit = st.tabs(["➕ Thêm cây mới", "✏️ Chỉnh sửa thông tin"])

        with tab_add:
            crop_select = st.selectbox("🌿 Chọn loại cây trồng", CROP_LIST,
                                       key="crop_select")
            if crop_select == "Khác":
                type_in = st.text_input(
                    "Nhập tên loại cây",
                    placeholder="Ví dụ: Ớt Aji Charapita",
                    key="add_type_custom"
                )
            else:
                type_in = crop_select

            name_in = st.text_input(
                "Tên định danh vụ",
                placeholder="Ví dụ: Ớt Aji - Lứa 01",
                key="add_name"
            )

            st.markdown("##### 📅 Các mốc thời gian")
            c1, c2 = st.columns(2)
            with c1:
                date_seed_soak  = st.date_input("🫧 Ngày ủ hạt",
                                                value=datetime.now(),
                                                key="date_seed_soak")
                date_transplant = st.date_input("🌱 Ngày trồng xuống đất",
                                                value=datetime.now(),
                                                key="date_transplant")
            with c2:
                date_seedling = st.date_input("🌿 Ngày gieo ươm",
                                              value=datetime.now(),
                                              key="date_seedling")
                st.caption("🍅 Ngày thu hoạch dự kiến do AI tự tính.")

            if st.button("🚀 Khởi tạo vườn", key="btn_init_farm"):
                if name_in.strip() and type_in.strip():
                    full_id = f"{name_in} | {type_in}"
                    data    = add_plant(
                        data, full_id,
                        date_transplant.strftime("%Y-%m-%d"),
                        extra={
                            "date_seed_soak": date_seed_soak.strftime("%Y-%m-%d"),
                            "date_seedling":  date_seedling.strftime("%Y-%m-%d"),
                            "date_harvest":   None,
                        }
                    )
                    save_data(data)
                    st.success(
                        f"Đã thêm **{name_in}**! "
                        "Hãy nhấn **🌱 Tạo quy trình chuẩn** để AI tính ngày thu hoạch."
                    )
                    st.rerun()
                else:
                    st.warning("Vui lòng điền đủ Tên và Loại cây.")

        with tab_edit:
            all_p = data.get("plants", [])
            if all_p:
                p_edit = st.selectbox(
                    "Chọn cây muốn sửa", all_p,
                    format_func=lambda x: x["name"],
                    key="sb_edit"
                )
                new_n = st.text_input("Sửa tên định danh",
                                      value=p_edit["name"], key="edit_name")

                st.markdown("##### 📅 Các mốc thời gian")
                c1, c2 = st.columns(2)
                with c1:
                    try:
                        val_seed_soak = (
                            datetime.strptime(p_edit["date_seed_soak"], "%Y-%m-%d")
                            if p_edit.get("date_seed_soak") else datetime.now()
                        )
                    except (ValueError, TypeError):
                        val_seed_soak = datetime.now()
                    new_seed_soak = st.date_input("🫧 Ngày ủ hạt",
                                                  value=val_seed_soak,
                                                  key="edit_seed_soak")
                    try:
                        val_transplant = datetime.strptime(p_edit["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        val_transplant = datetime.now()
                    new_d = st.date_input("🌱 Ngày trồng xuống đất",
                                          value=val_transplant, key="edit_date")

                with c2:
                    try:
                        val_seedling = (
                            datetime.strptime(p_edit["date_seedling"], "%Y-%m-%d")
                            if p_edit.get("date_seedling") else datetime.now()
                        )
                    except (ValueError, TypeError):
                        val_seedling = datetime.now()
                    new_seedling = st.date_input("🌿 Ngày gieo ươm",
                                                 value=val_seedling,
                                                 key="edit_seedling")
                    harvest_date = p_edit.get("date_harvest") or "Chưa có (AI sẽ tự tính)"
                    st.text_input("🍅 Dự kiến thu hoạch (do AI tính)",
                                  value=harvest_date, disabled=True,
                                  key="edit_harvest_display")

                if st.button("💾 Lưu cập nhật", key="btn_update"):
                    for p in data["plants"]:
                        if p["id"] == p_edit["id"]:
                            p["name"]           = new_n
                            p["date"]           = new_d.strftime("%Y-%m-%d")
                            p["date_seed_soak"] = new_seed_soak.strftime("%Y-%m-%d")
                            p["date_seedling"]  = new_seedling.strftime("%Y-%m-%d")
                    save_data(data)
                    st.success("Đã cập nhật!")
                    st.rerun()
            else:
                st.info("Chưa có cây nào để sửa.")

    plants_list = data.get("plants", [])

    if not plants_list:
        st.info("🌵 Vườn hiện tại chưa có cây. Hãy thêm cây mới ở trên.")
    else:
        for p in plants_list:
            with st.container(border=True):
                col_info, col_care, col_action = st.columns([1.2, 2.5, 0.8])

                with col_info:
                    st.subheader(f"🌿 {p['name']}")
                    try:
                        plant_date = datetime.strptime(p["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        plant_date = datetime.now()
                    age = max((datetime.now() - plant_date).days, 0)
                    st.write(f"⏱️ **{age} ngày tuổi**")

                    if p.get("date_seed_soak"):
                        st.caption(f"🫧 Ủ hạt: {p['date_seed_soak']}")
                    if p.get("date_seedling"):
                        st.caption(f"🌿 Gieo ươm: {p['date_seedling']}")
                    if p.get("date_harvest"):
                        st.caption(f"🍅 Thu hoạch dự kiến: {p['date_harvest']}")
                    else:
                        st.caption("🍅 Thu hoạch: Chưa có (nhấn Tạo quy trình)")

                    st.divider()

                    with st.popover("📖 Nhật ký vườn"):
                        st.write(f"📝 Ghi chép cho **{p['name']}**")
                        log_text = st.text_area(
                            "Hôm nay có gì mới?",
                            key=f"log_area_{p['id']}"
                        )
                        if st.button("Lưu nhật ký", key=f"btn_log_{p['id']}"):
                            if log_text.strip():
                                p.setdefault("logs", []).append({
                                    "d": datetime.now().strftime("%d/%m %H:%M"),
                                    "c": log_text.strip()
                                })
                                save_data(data)
                                st.success("Đã ghi sổ!")
                                st.rerun()
                            else:
                                st.warning("Nhật ký không được để trống.")
                        st.write("---")
                        recent_logs = list(reversed(p.get("logs", [])))[:3]
                        if recent_logs:
                            for log in recent_logs:
                                st.caption(f"📅 {log['d']}: {log['c']}")
                        else:
                            st.caption("Chưa có nhật ký nào.")

                with col_care:
                    parts     = p["name"].split("|", 1)
                    crop_type = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    st.markdown(f"📋 **Phác đồ tối ưu AI cho: {crop_type}**")

                    # ── Nút 1: Tạo quy trình chuẩn ──────────
                    if st.button("🌱 Tạo quy trình chuẩn",
                                 key=f"btn_std_{p['id']}"):
                        with st.spinner("AI đang tạo quy trình chuẩn..."):
                            try:
                                w_info     = safe_weather_str(weather)
                                std_prompt = f"""
Bạn là chuyên gia nông nghiệp hữu cơ. Trả lời BẰNG TIẾNG VIỆT.
Loại cây: {crop_type}
Ngày ủ hạt: {p.get('date_seed_soak', 'Chưa có')}
Ngày gieo ươm: {p.get('date_seedling', 'Chưa có')}
Ngày trồng xuống đất: {p.get('date', 'Chưa có')}
Thời tiết hiện tại: {w_info}

Hãy tạo QUY TRÌNH CHUẨN TOÀN VỤ từ ủ hạt đến thu hoạch:

### 🫧 GIAI ĐOẠN Ủ HẠT & GIEO ƯƠM
- Cách ủ hạt, nhiệt độ, độ ẩm cần thiết
- Thời gian nảy mầm dự kiến
- Chăm sóc cây con sau gieo

### 🌱 GIAI ĐOẠN CÂY CON (0-30 ngày)
- Dinh dưỡng: [loại phân, liều lượng, tần suất]
- Phòng bệnh: [sản phẩm sinh học ưu tiên]
- Lưu ý đặc biệt

### 🌿 GIAI ĐOẠN PHÁT TRIỂN (30-60 ngày)
- Dinh dưỡng: [loại phân, liều lượng, tần suất]
- Phòng sâu bệnh: [sản phẩm cụ thể]
- Kỹ thuật canh tác (bấm ngọn, tỉa cành...)

### 🌸 GIAI ĐOẠN RA HOA / KẾT TRÁI
- Dinh dưỡng tăng cường: [loại phân, liều lượng]
- Phòng rụng hoa, đậu trái
- Xử lý sâu bệnh thường gặp

### 🍅 GIAI ĐOẠN THU HOẠCH
- Dấu hiệu nhận biết đủ độ chín
- Cách thu hoạch đúng kỹ thuật
- Bảo quản sau thu hoạch

### ⚠️ CÁC BỆNH THƯỜNG GẶP & CÁCH XỬ LÝ
| Bệnh/Sâu | Dấu hiệu | Xử lý sinh học | Xử lý hóa học (dự phòng) |
|----------|----------|----------------|--------------------------|
| ...      | ...      | ...            | ...                      |

### 📆 DỰ KIẾN NGÀY THU HOẠCH
Dựa trên ngày trồng {p.get('date','?')} và đặc tính sinh trưởng của {crop_type},
hãy tính và ghi rõ 1 dòng theo đúng format sau (bắt buộc):
Ngày thu hoạch dự kiến: YYYY-MM-DD
"""
                                res      = model.generate_content(
                                    std_prompt,
                                    request_options={"timeout": 30}
                                )
                                std_text = getattr(res, "text", None)
                                if std_text:
                                    p["standard_recipe"] = std_text
                                    match = re.search(
                                        r"Ngày thu hoạch dự kiến:\s*(\d{4}-\d{2}-\d{2})",
                                        std_text
                                    )
                                    if match:
                                        p["date_harvest"] = match.group(1)
                                    save_data(data)
                                    st.session_state[f"std_view_{p['id']}"] = std_text
                                    st.rerun()
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    std_display = st.session_state.get(
                        f"std_view_{p['id']}", p.get("standard_recipe")
                    )
                    if std_display:
                        with st.expander("📋 XEM QUY TRÌNH CHUẨN", expanded=False):
                            st.markdown(std_display)

                    st.divider()

                    # ── Nút 2: Phân tích tình trạng hôm nay ─
                    if st.button("🔍 Phân tích tình trạng hôm nay",
                                 key=f"btn_analyze_{p['id']}"):
                        with st.spinner("AI đang phân tích..."):
                            try:
                                w_info        = safe_weather_str(weather)
                                current_logs  = " | ".join(
                                    [l["c"] for l in p.get("logs", [])]
                                )
                                warnings_list = weather.get("agri_warnings", [])

                                analyze_prompt = f"""
Bạn là chuyên gia nông nghiệp hữu cơ thực chiến. Trả lời BẰNG TIẾNG VIỆT.

=== THÔNG TIN CÂY ===
- Loại cây: {crop_type}
- Tuổi cây: {age} ngày (từ ngày trồng)
- Ngày ủ hạt: {p.get('date_seed_soak', 'Chưa có')}
- Ngày gieo ươm: {p.get('date_seedling', 'Chưa có')}
- Dự kiến thu hoạch: {p.get('date_harvest', 'Chưa có')}

=== THỜI TIẾT HIỆN TẠI ===
{w_info}
Cảnh báo: {', '.join(warnings_list) if warnings_list else 'Không có'}

=== NHẬT KÝ CHĂM SÓC GẦN NHẤT ===
{current_logs if current_logs else "Chưa có nhật ký"}

=== NHIỆM VỤ ===
### 🌡️ ĐÁNH GIÁ TÌNH TRẠNG HIỆN TẠI
- Cây đang ở giai đoạn sinh trưởng nào?
- Những vấn đề nguy cơ từ thời tiết và nhật ký?

### 💊 PHÂN BÓN CẦN BỔ SUNG NGAY
| Loại phân | Liều lượng | Cách bón | Thời điểm |
|-----------|-----------|----------|-----------|

### 🛡️ PHÒNG TRỊ SÂU BỆNH
| Đối tượng | Dấu hiệu cần theo dõi | Xử lý sinh học | Xử lý hóa học |
|-----------|----------------------|----------------|----------------|

### 📅 LỊCH VIỆC LÀM 7 NGÀY TỚI
| Ngày | Việc cần làm | Lưu ý |
|------|-------------|-------|

### ⚡ HÀNH ĐỘNG NGAY HÔM NAY
[Liệt kê 2-3 việc quan trọng nhất]
"""
                                res          = model.generate_content(
                                    analyze_prompt,
                                    request_options={"timeout": 30}
                                )
                                analyze_text = getattr(res, "text", None)
                                if analyze_text:
                                    p["daily_analysis"] = analyze_text
                                    save_data(data)
                                    st.session_state[
                                        f"analyze_view_{p['id']}"
                                    ] = analyze_text
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    analyze_display = st.session_state.get(
                        f"analyze_view_{p['id']}", p.get("daily_analysis")
                    )
                    if analyze_display:
                        with st.expander("🔍 KẾT QUẢ PHÂN TÍCH HÔM NAY",
                                         expanded=True):
                            st.markdown(analyze_display)

                    st.divider()

                    # ── Nút 3: Tối ưu 15 ngày tới ───────────
                    if st.button("🧠 AI: Tối ưu 15 ngày tới",
                                 key=f"btn_opt_{p['id']}"):
                        with st.spinner("Đang tổng hợp lịch sử & phân tích..."):
                            try:
                                w_info       = safe_weather_str(weather)
                                current_logs = " | ".join(
                                    [l["c"] for l in p.get("logs", [])]
                                )
                                past_seasons = get_crop_history(data, crop_type)
                                season_ctx   = build_season_context(past_seasons)
                                season_count = len(past_seasons)

                                prompt_15 = f"""
Bạn là chuyên gia nông nghiệp hữu cơ cấp cao. Trả lời BẰNG TIẾNG VIỆT.

=== THÔNG TIN CÂY HIỆN TẠI ===
- Loại cây: {crop_type}
- Ngày ủ hạt: {p.get('date_seed_soak', 'Chưa có')}
- Ngày gieo ươm: {p.get('date_seedling', 'Chưa có')}
- Ngày trồng xuống đất: {p.get('date', 'Chưa có')}
- Tuổi cây tính từ ngày trồng: {age} ngày
- Dự kiến thu hoạch: {p.get('date_harvest', 'Chưa có')}
- Thời tiết hiện tại: {w_info}
- Nhật ký vụ này: {current_logs if current_logs else "Chưa có dữ liệu"}

=== DỮ LIỆU HỌC MÁY TỪ {season_count} VỤ TRƯỚC ===
{season_ctx}

=== NHIỆM VỤ ===
### 📊 PHÂN TÍCH GIAI ĐOẠN SINH TRƯỞNG
### 📊 HỌC TỪ VỤ TRƯỚC
### 🌿 DINH DƯỠNG
### 🛡️ BẢO VỆ THỰC VẬT
### 🔧 ĐIỀU CHỈNH TỪ NHẬT KÝ
### 📅 LỊCH 15 NGÀY
| Ngày  | Giai đoạn | Việc cần làm |
|-------|-----------|-------------|
| 1-5   | ...       | ...         |
| 6-10  | ...       | ...         |
| 11-15 | ...       | ...         |
"""
                                res         = model.generate_content(
                                    prompt_15,
                                    request_options={"timeout": 30}
                                )
                                recipe_text = getattr(res, "text", None)
                                if recipe_text:
                                    p["optimized_recipe"] = recipe_text
                                    save_data(data)
                                    st.session_state[
                                        f"st_view_{p['id']}"
                                    ] = recipe_text
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi kết nối AI: {e}")

                    plan_display = st.session_state.get(
                        f"st_view_{p['id']}", p.get("optimized_recipe")
                    )
                    if plan_display:
                        with st.expander("📍 XEM QUY TRÌNH TỐI ƯU", expanded=False):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chưa có quy trình tối ưu. Hãy nhấn nút AI.")

                with col_action:
                    st.caption("⚙️ Thao tác")
                    with st.popover("🗑️ Kết thúc vụ"):
                        st.warning(f"Kết thúc vụ **{p['name']}**?")
                        st.caption("Nhật ký & quy trình sẽ được lưu để AI học cho vụ sau.")
                        if st.button("✔️ Xác nhận",
                                     key=f"btn_del_{p['id']}", type="primary"):
                            data = archive_and_delete_plant(data, p["id"])
                            st.rerun()

                    if weather.get("temp") is not None:
                        st.metric("🌡️ Nhiệt độ", f"{weather['temp']}°C")
                        st.metric("💧 Độ ẩm",    f"{weather['hum']}%")
                        if weather.get("wind") is not None:
                            st.metric("💨 Gió", f"{weather['wind']} km/h")

# =============================================================
# 📸 CAMERA CHẨN ĐOÁN
# =============================================================

elif menu == "📸 Camera Chẩn đoán":
    back_button()
    st.title("🩺 Bác sĩ AI Thực địa")

    st.info("""
    💡 **Hướng dẫn chụp ảnh để AI chẩn đoán chính xác nhất:**
    1. Đảm bảo đủ ánh sáng để thấy rõ màu sắc lá.
    2. Chụp cận cảnh vết bệnh, sâu hại hoặc mặt dưới của lá.
    3. Nếu có thể, để một phần lá lành trong khung hình để AI đối chiếu.
    """)

    lat_gps = st.session_state.get("gps_lat") or DEFAULT_LAT
    lon_gps = st.session_state.get("gps_lon") or DEFAULT_LON
    w_meteo = fetch_meteo_weather(lat_gps, lon_gps)

    st.sidebar.metric("🌡️ Nhiệt độ thực địa", f"{w_meteo['temp']}°C")
    st.sidebar.metric("💧 Độ ẩm thực địa",    f"{w_meteo['hum']}%")
    st.sidebar.caption(f"🌤️ {w_meteo.get('desc', '')}")

    all_plants    = data.get("plants", [])
    plant_names   = [p["name"] for p in all_plants]
    plant_context = (
        ", ".join(plant_names) if plant_names else "Hệ thống tự nhận diện"
    )

    selected_plant = None
    if all_plants:
        selected_plant = st.selectbox(
            "📌 Gắn kết quả chẩn đoán vào cây (tùy chọn):",
            [None] + all_plants,
            format_func=lambda x: "— Không gắn —" if x is None else x["name"],
            key="sb_cam_plant"
        )

    img_file = st.camera_input("Chụp ảnh cây cần chẩn đoán")

    if img_file:
        image = Image.open(img_file)
        st.image(image, caption="Ảnh thực địa", width=500)

        if st.button("🚀 Phân tích & Kê đơn thuốc",
                     type="primary", key="btn_cam_ai"):

            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="JPEG",
                                      quality=75, optimize=True)
            img_bytes = buf.getvalue()

            age_ctx = ""
            if selected_plant:
                try:
                    plant_date = datetime.strptime(
                        selected_plant["date"], "%Y-%m-%d"
                    )
                    age_days = max((datetime.now() - plant_date).days, 0)
                    age_ctx  = f"Cây đang ở ngày thứ {age_days} kể từ khi trồng."
                except (ValueError, KeyError):
                    age_ctx = ""

            warnings_list = weather.get("agri_warnings", [])
            full_prompt   = f"""
Bạn là Bác sĩ cây trồng chuyên nghiệp với 20 năm kinh nghiệm thực địa tại Đông Nam Á.

DANH MỤC CÂY TRONG VƯỜN HIỆN CÓ: {plant_context}
THỜI TIẾT THỰC ĐỊA (Meteo): {w_meteo['temp']}°C, độ ẩm {w_meteo['hum']}% ({w_meteo.get('desc', '')})
CẢNH BÁO NÔNG NGHIỆP: {', '.join(warnings_list) if warnings_list else 'Không có'}
{age_ctx}

Nhiệm vụ — trả lời BẰNG TIẾNG VIỆT theo đúng cấu trúc:

### 🌿 1. XÁC ĐỊNH CÂY
Dựa vào ảnh, đây là cây gì? Nếu trùng tên trong danh mục vườn, gọi đúng tên định danh đó.

### 🦠 2. CHẨN ĐOÁN
- Tên bệnh / sâu hại và tác nhân (Nấm / Vi khuẩn / Virus / Côn trùng).
- Dấu hiệu nhận biết cụ thể từ ảnh (màu sắc, hình dạng, vị trí vết bệnh).
- Giai đoạn bệnh: [Sơ nhiễm / Đang phát triển / Nặng]

### 🌧️ 3. LIÊN HỆ THỜI TIẾT
Với độ ẩm {w_meteo['hum']}% hiện tại, bệnh có xu hướng lây lan thế nào? Dự báo 3-5 ngày tới?

### 💊 4. PHÁC ĐỒ ĐIỀU TRỊ
- **Bước 1 — Xử lý ngay:** Cắt tỉa / cách ly nếu cần.
- **Bước 2 — Sinh học (Ưu tiên):** Tên sản phẩm, liều lượng, cách dùng.
- **Bước 3 — Hóa học (Khi cần):** Hoạt chất, liều lượng, lưu ý PHI.

### 📅 5. PHÒNG NGỪA 7 NGÀY TỚI
Lịch chăm sóc ngắn gọn để không tái phát.

### 📈 6. TIÊN LƯỢNG
- Mức độ nguy hiểm: [🟢 Thấp / 🟡 Trung bình / 🔴 Cao / ⛔ Khẩn cấp]
- Khuyến nghị khẩn: [Hành động cần làm NGAY trong 24h]

Ngôn ngữ: bình dân, dễ hiểu cho nông dân Việt Nam.
"""
            with st.spinner("Bác sĩ AI đang đối chiếu dữ liệu vườn và thời tiết..."):
                try:
                    img_part = {"mime_type": "image/jpeg", "data": img_bytes}
                    res      = model.generate_content(
                        [full_prompt, img_part],
                        request_options={"timeout": 30}
                    )
                    result = getattr(res, "text", None)
                    if result:
                        st.session_state["last_diagnosis"] = {
                            "result":  result,
                            "plant":   selected_plant,
                            "weather": w_meteo,
                        }
                    else:
                        st.warning("⚠️ AI không phản hồi. Vui lòng thử lại.")
                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")
                    st.info("Kiểm tra lại kết nối mạng hoặc GEMINI_API_KEY.")

    diag = st.session_state.get("last_diagnosis")
    if diag:
        st.markdown("---")
        st.subheader("🔬 Kết quả chẩn đoán")
        st.markdown(diag["result"])

        if diag.get("plant"):
            plant_name = diag["plant"]["name"]
            if st.button(
                f"💾 Lưu chẩn đoán vào nhật ký '{plant_name}'",
                key="btn_save_diag"
            ):
                summary = diag["result"][:120].rsplit(" ", 1)[0] + "..."
                for p in data["plants"]:
                    if p["id"] == diag["plant"]["id"]:
                        p.setdefault("logs", []).append({
                            "d": datetime.now().strftime("%d/%m %H:%M"),
                            "c": f"🩺 AI Chẩn đoán: {summary}"
                        })
                        break
                save_data(data)
                del st.session_state["last_diagnosis"]
                st.success(f"✅ Đã lưu vào nhật ký **{plant_name}**!")
                st.rerun()

# =============================================================
# 💬 AI ASSISTANT
# =============================================================

elif menu == "💬 AI Assistant":
    back_button()
    st.title("💬 Trợ lý Kỹ thuật")

    city     = weather.get("city", "Đang xác định...")
    temp_now = weather.get("temp", "?")
    hum_now  = weather.get("hum",  "?")
    wind_now = weather.get("wind", "?")
    desc_now = weather.get("desc", "")
    st.caption(
        f"📍 {city}: {temp_now}°C — {hum_now}% ẩm"
        f" — Gió {wind_now} km/h — {desc_now}"
    )

    chat_container = st.container()
    with chat_container:
        for chat in data.get("chat_history", []):
            with st.chat_message("user"):
                st.write(chat["user"])
            with st.chat_message("assistant"):
                st.markdown(chat["ai"])

    if prompt := st.chat_input("Hỏi AI về kỹ thuật vườn, phân bón, sâu bệnh..."):
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("🤖 AI đang phân tích dữ liệu..."):
            try:
                w_ctx = (
                    f"Nhiệt độ {temp_now}°C, Độ ẩm {hum_now}%, "
                    f"Gió {wind_now} km/h, Thời tiết: {desc_now}"
                )
                full_prompt = f"""
Bạn là Chuyên gia Nông nghiệp Công nghệ cao.
Dữ liệu thời tiết hiện tại tại {city}: {w_ctx}
Câu hỏi của nông dân: {prompt}

Yêu cầu:
- Trả lời bằng tiếng Việt.
- Tập trung giải pháp kỹ thuật, ưu tiên hữu cơ/sinh học.
- Sử dụng Markdown (###, **, -) để trình bày đẹp mắt.
"""
                response = model.generate_content(
                    full_prompt,
                    request_options={"timeout": 30}
                )
                ai_res = (
                    response.text if hasattr(response, "text")
                    else "⚠️ AI không thể trả lời câu hỏi này."
                )

                with st.chat_message("assistant"):
                    st.markdown(ai_res)

                add_chat(data, prompt, ai_res)
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Lỗi kết nối AI: {e}")
                st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets.")
