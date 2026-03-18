# -*- coding: utf-8 -*-
"""
app.py - GREEN FARM
Chạy: streamlit run app.py
"""

import io
import re
import requests
import pandas as pd
import altair as alt
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
from weather import (
    get_weather, get_city_name,
    get_forecast_7day, get_disease_pressure_48h
)

# =============================================================
# CẤU HÌNH GEMINI
# =============================================================

try:
    GENAI_KEY    = st.secrets["GEMINI_API_KEY"]
    GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash")
except (KeyError, FileNotFoundError):
    GENAI_KEY    = ""
    GEMINI_MODEL = "gemini-2.5-flash"

genai.configure(api_key=GENAI_KEY)
try:
    GENAI_KEY    = st.secrets["GEMINI_API_KEY"]
    GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-2.0-flash")
except (KeyError, FileNotFoundError):
    GENAI_KEY    = ""
    GEMINI_MODEL = "gemini-2.0-flash"

genai.configure(api_key=GENAI_KEY)


@st.cache_resource
def get_gemini_model(model_name: str):
    return genai.GenerativeModel(model_name)


model = get_gemini_model(GEMINI_MODEL)

# =============================================================
# CONSTANTS
# =============================================================

DEFAULT_LAT, DEFAULT_LON = 16.45780, 107.56150

CROP_LIST = [
    "Ớt Aji Charapita", "Ớt Chỉ thiên", "Ớt Xiêm",
    "Bầu", "Mai vàng", "Cà chua Beef", "Dưa leo",
    "Chanh", "Cà tím", "Bắp cải", "Xà lách",
    "Rau muống", "Húng quế", "Cần tây", "Khác"
]

WMO_MAP = {
    0: "Trời quang",     1: "Ít mây",           2: "Mây rải rác",
    3: "Nhiều mây",     45: "Sương mù",         48: "Sương mù có băng",
    51: "Mưa phùn nhẹ", 53: "Mưa phùn",        55: "Mưa phùn dày",
    61: "Mưa nhỏ",      63: "Mưa vừa",          65: "Mưa to",
    80: "Mưa rào nhẹ",  81: "Mưa rào",          82: "Mưa rào nặng",
    95: "Dông bão",     96: "Dông có mưa đá",   99: "Dông mưa đá lớn",
}

RISK_COLOR = {
    "low":      "🟢",
    "medium":   "🟡",
    "high":     "🔴",
    "critical": "⛔",
    "unknown":  "⚪"
}

# =============================================================
# HELPERS
# =============================================================

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
            f"--- Vụ {i} ({s.get('date_start','')} → {s.get('date_end','')}) ---"
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
    return {
        "temp": None, "hum": None, "wind": None,
        "rain": None, "desc": "Đang tải...",
        "city": "Đang xác định vị trí...",
        "lat": DEFAULT_LAT, "lon": DEFAULT_LON,
        "vpd": None, "vpd_status": {},
        "agri_warnings": []
    }


def fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")
    except Exception:
        return d

# =============================================================
# STREAMLIT CONFIG
# =============================================================

st.set_page_config(page_title="GREEN FARM", layout="wide", page_icon="🌿")

# =============================================================
# XÁC THỰC
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
# GPS
# =============================================================

if "gps_lat" not in st.session_state:
    st.session_state["gps_lat"]      = None
    st.session_state["gps_lon"]      = None
    st.session_state["gps_resolved"] = False

if not st.session_state["gps_resolved"]:
    with st.spinner("📍 Đang xác định vị trí GPS thực tế..."):
        loc = get_geolocation()
    if loc and isinstance(loc, dict) and "coords" in loc:
        try:
            new_lat = float(loc["coords"]["latitude"])
            new_lon = float(loc["coords"]["longitude"])
            if abs(new_lat) > 0.01 or abs(new_lon) > 0.01:
                st.session_state["gps_lat"]      = new_lat
                st.session_state["gps_lon"]      = new_lon
                st.session_state["gps_resolved"] = True
        except (KeyError, ValueError, TypeError):
            pass

if st.session_state["gps_lat"] is None:
    st.session_state["gps_lat"] = DEFAULT_LAT
    st.session_state["gps_lon"] = DEFAULT_LON

# =============================================================
# CACHE WEATHER & FORECAST
# =============================================================

@st.cache_data(ttl=600)
def fetch_weather_data(lat: float, lon: float) -> dict:
    return get_weather(lat=lat, lon=lon)


@st.cache_data(ttl=600)
def fetch_meteo_direct(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
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
            "wind": round(curr.get("wind_speed_10m") or 0.0, 1),
            "desc": WMO_MAP.get(code, "Không xác định"),
            "code": code,
        }
    except Exception:
        pass
    return {"temp": None, "hum": None, "wind": None, "desc": "N/A", "code": -1}


@st.cache_data(ttl=1800)
def fetch_forecast_7day(lat: float, lon: float) -> list:
    return get_forecast_7day(lat, lon)


@st.cache_data(ttl=600)
def fetch_disease_pressure(lat: float, lon: float) -> dict:
    return get_disease_pressure_48h(lat, lon)


# =============================================================
# TẢI DỮ LIỆU
# =============================================================

data    = load_data()
lat     = st.session_state["gps_lat"]
lon     = st.session_state["gps_lon"]
_w      = fetch_weather_data(lat, lon)
weather = _w if _w is not None else get_weather_safe()

# =============================================================
# SIDEBAR
# =============================================================

with st.sidebar:
    st.title("🌿 GREEN FARM")
    st.caption(f"📍 {weather.get('city', '...')}")
    gps_source = "📡 GPS thực" if st.session_state["gps_resolved"] else "📌 Mặc định"
    st.caption(f"{gps_source}: {lat:.4f}, {lon:.4f}")

    menu_options = [
        "📊 Dashboard",
        "🌱 Quản lý Cây trồng",
        "🩺 Bác sĩ AI & Camera",
        "💬 Trợ lý Kỹ thuật",
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


def back_button():
    if "prev_menu" in st.session_state:
        if st.button("⬅️ Quay lại"):
            st.session_state["menu_choice"] = st.session_state["prev_menu"]
            st.rerun()

# =============================================================
# COMPONENT: DỰ BÁO 7 NGÀY
# =============================================================

def render_forecast_7day(lat: float, lon: float):
    st.markdown("### 🗓️ Dự báo 7 ngày (Tầm nhìn xa)")
    forecast = fetch_forecast_7day(lat, lon)
    if not forecast:
        st.warning("Không lấy được dự báo 7 ngày.")
        return

    cols = st.columns(7)
    for i, day in enumerate(forecast):
        with cols[i]:
            risk    = day["risk"]
            icon    = RISK_COLOR.get(risk, "⚪")
            label   = "Hôm nay" if i == 0 else fmt_date(day["date"])
            content = (
                f"**{label}**\n\n"
                f"{icon}\n\n"
                f"↑{day['temp_max']:.0f}° ↓{day['temp_min']:.0f}°\n\n"
                f"💧{day['hum_max']:.0f}%"
                + (f"\n\n🌧️{day['rain']:.1f}mm" if day["rain"] > 0 else "")
                + f"\n\n_{day['desc'][:14]}_"
            )
            if risk == "critical":
                st.error(content)
            elif risk == "high":
                st.warning(content)
            elif risk == "medium":
                st.info(content)
            else:
                st.success(content)

    st.caption("🟢 An toàn  🟡 Cần theo dõi  🔴 Nguy cơ cao  ⛔ Cực kỳ nguy hiểm")

# =============================================================
# COMPONENT: ÁP LỰC BỆNH 48H
# =============================================================

def render_disease_pressure_48h(lat: float, lon: float):
    st.markdown("### 🦠 Áp lực bệnh 48h")
    dp = fetch_disease_pressure(lat, lon)

    level      = dp.get("level", "unknown")
    score      = dp.get("score", 0)
    hours_risk = dp.get("hours_risk", 0)
    peak_time  = dp.get("peak_time", "")
    warnings   = dp.get("warnings", [])

    col1, col2, col3 = st.columns(3)
    icon = RISK_COLOR.get(level, "⚪")
    col1.metric("Mức độ rủi ro", f"{icon} {level.upper()}", f"Score: {score}/100")
    col2.metric("Giờ nguy hiểm", f"{hours_risk}h / 48h")
    col3.metric("Cao điểm",      peak_time if peak_time else "N/A")

    st.progress(min(score, 100))

    for w in warnings:
        if level in ("critical", "high"):
            st.error(w)
        elif level == "medium":
            st.warning(w)
        else:
            st.success(w)

    # Biểu đồ áp lực theo giờ
    hourly = dp.get("hourly", [])
    if hourly:
        df = pd.DataFrame(hourly)
        df["color"] = df["risk"].map({
            "high":   "#e74c3c",
            "medium": "#f39c12",
            "low":    "#27ae60"
        })
        df_display = df[df.index % 2 == 0].copy()

        chart = (
            alt.Chart(df_display)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("time:N",
                        title="Giờ trong ngày",
                        sort=None,
                        axis=alt.Axis(labelAngle=-45, labelFontSize=10)),
                y=alt.Y("score:Q",
                        title="Điểm rủi ro (0-10)",
                        scale=alt.Scale(domain=[0, 10])),
                color=alt.Color("color:N", scale=None, legend=None),
                tooltip=[
                    alt.Tooltip("time:N",  title="Giờ"),
                    alt.Tooltip("temp:Q",  title="Nhiệt độ °C"),
                    alt.Tooltip("hum:Q",   title="Độ ẩm %"),
                    alt.Tooltip("score:Q", title="Điểm rủi ro"),
                    alt.Tooltip("risk:N",  title="Mức độ"),
                ]
            )
            .properties(
                title=alt.TitleParams(
                    "⏱️ Diễn biến áp lực bệnh 48h tới",
                    fontSize=14, anchor="start"
                ),
                height=220
            )
        )
        threshold = (
            alt.Chart(pd.DataFrame({"y": [5]}))
            .mark_rule(color="#e74c3c", strokeDash=[4, 4], size=1.5)
            .encode(y="y:Q")
        )
        st.altair_chart(chart + threshold, use_container_width=True)
        st.caption("📊 Đường đứt đỏ = ngưỡng cảnh báo | Cập nhật mỗi 10 phút")

# =============================================================
# COMPONENT: SO KHỚP 3 BÊN AI
# =============================================================

def render_three_way_match(p: dict, crop_type: str, age: int):
    st.markdown("### 🧠 Bộ não nhắc nhở (So khớp 3 bên)")

    if st.button("🔄 Phân tích & Nhắc việc", key=f"btn_3way_{p['id']}"):
        current_logs  = " | ".join([l["c"] for l in p.get("logs", [])[-5:]])
        std_recipe    = p.get("standard_recipe", "Chưa có quy trình chuẩn.")[:500]
        warnings_list = weather.get("agri_warnings", [])
        dp            = fetch_disease_pressure(lat, lon)

        prompt = f"""
Bạn là AI quản lý vườn thông minh, chuyên phân tích dữ liệu thực địa.
Trả lời BẰNG TIẾNG VIỆT.

=== NGUỒN 1: NHẬT KÝ THỰC TẾ (phân tích từ khóa) ===
Cây: {crop_type} | Tuổi: {age} ngày
Nhật ký gần nhất: {current_logs if current_logs else "Chưa có"}

Hãy nhận diện các từ khóa quan trọng trong nhật ký:
- Triệu chứng bệnh: (vàng lá, héo, đốm, thối, rụng, cháy, cuộn...)
- Hành động đã làm: (tưới, bón, phun, cắt, tỉa...)
- Vấn đề chưa xử lý: (bọ, sâu, nhện, rệp, nấm...)
- Khoảng thời gian: (hôm qua, 3 ngày, tuần trước...)

=== NGUỒN 2: THỜI TIẾT + ÁP LỰC BỆNH ===
Hiện tại: {safe_weather_str(weather)}
Cảnh báo: {', '.join(warnings_list) if warnings_list else 'Không có'}
Áp lực bệnh 48h: {dp.get('level','?').upper()}
  - Score: {dp.get('score',0)}/100
  - Số giờ nguy hiểm: {dp.get('hours_risk',0)}h
  - Cao điểm: {dp.get('peak_time','?')}

=== NGUỒN 3: QUY TRÌNH CHUẨN ===
{std_recipe}

=== NHIỆM VỤ ===
Dựa trên 3 nguồn trên, xác định CHÍNH XÁC những việc bị bỏ sót hoặc cần làm ngay.

Ưu tiên theo thứ tự:
1. Việc KHẨN CẤP (áp lực bệnh cao + triệu chứng trong nhật ký)
2. Việc QUAN TRỌNG (quy trình chuẩn yêu cầu nhưng chưa thấy trong nhật ký)
3. Việc NÊN LÀM (phòng ngừa dựa trên dự báo thời tiết)

Format BẮT BUỘC, mỗi việc 1 dòng:
VIEC_1: [🚨/⚠️/💡 emoji mức độ] [tên việc ngắn gọn] | [lý do cụ thể dựa trên dữ liệu]
VIEC_2: ...
(tối đa 5 việc, không giải thích thêm)
"""
        with st.spinner("AI đang so sánh 3 nguồn dữ liệu..."):
            try:
                res  = model.generate_content(prompt, request_options={"timeout": 20})
                text = getattr(res, "text", "") or ""
                tasks = []
                for line in text.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("VIEC_") and ":" in line:
                        task_text = line.split(":", 1)[1].strip()
                        if task_text:
                            tasks.append(task_text)
                if not tasks:
                    tasks = [
                        line.strip() for line in text.strip().split("\n")
                        if line.strip() and len(line.strip()) > 10
                    ][:5]
                if tasks:
                    st.session_state[f"tasks_3way_{p['id']}"] = tasks
                    p["tasks_3way"] = tasks
                    save_data(data)
                    st.rerun()
            except Exception as e:
                st.error(f"Lỗi AI so khớp: {e}")

    tasks = st.session_state.get(
        f"tasks_3way_{p['id']}",
        p.get("tasks_3way", [])
    )
    if tasks:
        st.markdown("---")
        st.markdown("#### 📋 Danh sách việc cần làm")

        urgent  = [t for t in tasks if "🚨" in t]
        warning = [t for t in tasks if "⚠️" in t]
        tip     = [t for t in tasks if "💡" in t]

        c1, c2, c3 = st.columns(3)
        c1.metric("🚨 Khẩn cấp",   len(urgent))
        c2.metric("⚠️ Quan trọng", len(warning))
        c3.metric("💡 Nên làm",    len(tip))

        st.markdown("---")

        for idx, task in enumerate(tasks):
            parts     = task.split("|", 1)
            task_name = parts[0].strip()
            reason    = parts[1].strip() if len(parts) > 1 else ""

            if "🚨" in task_name:
                container = st.error
            elif "⚠️" in task_name:
                container = st.warning
            else:
                container = st.info

            col_main, col_btn = st.columns([5, 1])
            with col_main:
                container(
                    f"**{task_name}**\n\n_{reason}_"
                    if reason else f"**{task_name}**"
                )
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Xong",
                             key=f"done_3way_{p['id']}_{idx}",
                             use_container_width=True):
                    p.setdefault("logs", []).append({
                        "d": datetime.now().strftime("%d/%m %H:%M"),
                        "c": f"✅ Đã thực hiện (AI nhắc): {task_name[:80]}"
                    })
                    remaining = [t for j, t in enumerate(tasks) if j != idx]
                    st.session_state[f"tasks_3way_{p['id']}"] = remaining
                    p["tasks_3way"] = remaining
                    save_data(data)
                    st.success("✅ Đã ghi vào nhật ký!")
                    st.rerun()

        if st.button("🎉 Hoàn thành tất cả",
                     key=f"done_all_{p['id']}",
                     type="primary",
                     use_container_width=True):
            for task in tasks:
                parts     = task.split("|", 1)
                task_name = parts[0].strip()
                p.setdefault("logs", []).append({
                    "d": datetime.now().strftime("%d/%m %H:%M"),
                    "c": f"✅ Đã thực hiện: {task_name[:80]}"
                })
            st.session_state.pop(f"tasks_3way_{p['id']}", None)
            p["tasks_3way"] = []
            save_data(data)
            st.success("🎉 Tuyệt vời! Đã hoàn thành tất cả việc hôm nay!")
            st.rerun()

# =============================================================
# 📊 DASHBOARD
# =============================================================

if menu == "📊 Dashboard":
    back_button()
    st.title("📊 Quan trắc VPD & Thời tiết")
    st.markdown(f"📍 **{weather.get('city', '...')}**")

    if weather.get("temp") is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌡️ Nhiệt độ",  f"{weather['temp']}°C")
        c2.metric("💧 Độ ẩm",     f"{weather['hum']}%")
        c3.metric("🌧️ Mưa",       f"{weather['rain']} mm")
        c4.metric("🌤️ Thời tiết", weather["desc"])

        if weather.get("wind") is not None:
            wind_val   = weather["wind"]
            wind_delta = (
                "⛔ Rất mạnh" if wind_val >= 40
                else "⚠️ Vừa"  if wind_val >= 20
                else "✅ Nhẹ"
            )
            st.metric("💨 Gió", f"{wind_val} km/h", wind_delta)

        # VPD — dùng từ weather dict, không tính lại
        vpd        = weather.get("vpd")
        vpd_status = weather.get("vpd_status", {})

        if vpd is not None:
            st.markdown(
                f"### 💨 Chỉ số VPD: `{vpd:.2f} kPa` "
                f"— {vpd_status.get('label', '')}"
            )
            if vpd_status.get("warning"):
                if vpd_status["level"] in ("danger_low", "danger_high"):
                    st.error(vpd_status["warning"])
                else:
                    st.warning(vpd_status["warning"])
        else:
            st.markdown("### 💨 Chỉ số VPD: Đang tải...")

        warnings = weather.get("agri_warnings", [])
        if warnings:
            st.markdown("### 🚨 Cảnh báo Nông nghiệp")
            for w in warnings:
                st.info(w)

        st.divider()
        render_forecast_7day(lat, lon)
        st.divider()
        render_disease_pressure_48h(lat, lon)

    else:
        st.info("⏳ Đang tải dữ liệu thời tiết...")

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
            type_in = (
                st.text_input("Nhập tên loại cây",
                              placeholder="Ví dụ: Ớt Aji Charapita",
                              key="add_type_custom")
                if crop_select == "Khác" else crop_select
            )
            name_in = st.text_input("Tên định danh vụ",
                                    placeholder="Ví dụ: Ớt Aji - Lứa 01",
                                    key="add_name")
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
                st.caption("🍅 Ngày thu hoạch do AI tự tính sau khi tạo quy trình.")

            if st.button("🚀 Khởi tạo vườn", key="btn_init_farm"):
                if name_in.strip() and type_in.strip():
                    data = add_plant(
                        data, f"{name_in} | {type_in}",
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
                        "Nhấn 🌱 Tạo quy trình chuẩn để AI tính ngày thu hoạch."
                    )
                    st.rerun()
                else:
                    st.warning("Vui lòng điền đủ Tên và Loại cây.")

        with tab_edit:
            all_p = data.get("plants", [])
            if all_p:
                p_edit = st.selectbox("Chọn cây muốn sửa", all_p,
                                      format_func=lambda x: x["name"],
                                      key="sb_edit")
                new_n = st.text_input("Sửa tên định danh",
                                      value=p_edit["name"], key="edit_name")
                st.markdown("##### 📅 Các mốc thời gian")
                c1, c2 = st.columns(2)
                with c1:
                    try:
                        val_ss = (datetime.strptime(p_edit["date_seed_soak"], "%Y-%m-%d")
                                  if p_edit.get("date_seed_soak") else datetime.now())
                    except (ValueError, TypeError):
                        val_ss = datetime.now()
                    new_ss = st.date_input("🫧 Ngày ủ hạt",
                                           value=val_ss, key="edit_seed_soak")
                    try:
                        val_tr = datetime.strptime(p_edit["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        val_tr = datetime.now()
                    new_d = st.date_input("🌱 Ngày trồng xuống đất",
                                          value=val_tr, key="edit_date")
                with c2:
                    try:
                        val_sl = (datetime.strptime(p_edit["date_seedling"], "%Y-%m-%d")
                                  if p_edit.get("date_seedling") else datetime.now())
                    except (ValueError, TypeError):
                        val_sl = datetime.now()
                    new_sl = st.date_input("🌿 Ngày gieo ươm",
                                           value=val_sl, key="edit_seedling")
                    st.text_input("🍅 Dự kiến thu hoạch (do AI tính)",
                                  value=p_edit.get("date_harvest") or "Chưa có",
                                  disabled=True, key="edit_harvest_display")

                if st.button("💾 Lưu cập nhật", key="btn_update"):
                    for p in data["plants"]:
                        if p["id"] == p_edit["id"]:
                            p["name"]           = new_n
                            p["date"]           = new_d.strftime("%Y-%m-%d")
                            p["date_seed_soak"] = new_ss.strftime("%Y-%m-%d")
                            p["date_seedling"]  = new_sl.strftime("%Y-%m-%d")
                    save_data(data)
                    st.success("Đã cập nhật!")
                    st.rerun()
            else:
                st.info("Chưa có cây nào để sửa.")

    plants_list = data.get("plants", [])
    if not plants_list:
        st.info("🌵 Vườn hiện tại chưa có cây. Hãy thêm cây mới ở trên.")
    else:
        with st.expander("🦠 Áp lực bệnh 48h toàn vườn", expanded=False):
            render_disease_pressure_48h(lat, lon)

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
                    st.caption(
                        f"🍅 Thu hoạch: {p['date_harvest']}"
                        if p.get("date_harvest") else "🍅 Thu hoạch: Chưa có"
                    )
                    st.divider()
                    with st.popover("📖 Nhật ký vườn"):
                        st.write(f"📝 Ghi chép cho **{p['name']}**")
                        log_text = st.text_area("Hôm nay có gì mới?",
                                                key=f"log_area_{p['id']}")
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
                        recent_logs = list(reversed(p.get("logs", [])))[:5]
                        if recent_logs:
                            for log in recent_logs:
                                st.caption(f"📅 {log['d']}: {log['c']}")
                        else:
                            st.caption("Chưa có nhật ký nào.")

                with col_care:
                    parts     = p["name"].split("|", 1)
                    crop_type = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    st.markdown(f"📋 **Phác đồ tối ưu AI cho: {crop_type}**")

                    # Nút 1: Tạo quy trình chuẩn
                    if st.button("🌱 Tạo quy trình chuẩn", key=f"btn_std_{p['id']}"):
                        with st.spinner("AI đang tạo quy trình chuẩn..."):
                            try:
                                res = model.generate_content(
                                    f"""Bạn là chuyên gia nông nghiệp hữu cơ. Trả lời BẰNG TIẾNG VIỆT.
Loại cây: {crop_type}
Ngày ủ hạt: {p.get('date_seed_soak', 'Chưa có')}
Ngày gieo ươm: {p.get('date_seedling', 'Chưa có')}
Ngày trồng xuống đất: {p.get('date', 'Chưa có')}
Thời tiết hiện tại: {safe_weather_str(weather)}

Hãy tạo QUY TRÌNH CHUẨN TOÀN VỤ từ ủ hạt đến thu hoạch:

### 🫧 GIAI ĐOẠN Ủ HẠT & GIEO ƯƠM
### 🌱 GIAI ĐOẠN CÂY CON (0-30 ngày)
### 🌿 GIAI ĐOẠN PHÁT TRIỂN (30-60 ngày)
### 🌸 GIAI ĐOẠN RA HOA / KẾT TRÁI
### 🍅 GIAI ĐOẠN THU HOẠCH
### ⚠️ CÁC BỆNH THƯỜNG GẶP & CÁCH XỬ LÝ
| Bệnh/Sâu | Dấu hiệu | Xử lý sinh học | Xử lý hóa học |
|----------|----------|----------------|---------------|

### 📆 DỰ KIẾN NGÀY THU HOẠCH
QUAN TRỌNG: Mỗi giai đoạn tối đa 3 gạch đầu dòng. Ngắn gọn, súc tích.
Ngày thu hoạch dự kiến: YYYY-MM-DD""",
                                    request_options={"timeout": 60}
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
                                    st.warning("AI không trả về kết quả.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    std_display = st.session_state.get(
                        f"std_view_{p['id']}", p.get("standard_recipe"))
                    if std_display:
                        with st.expander("📋 Xem quy trình chuẩn", expanded=False):
                            st.markdown(std_display)

                    st.divider()

                    # Nút 2: Phân tích hôm nay
                    if st.button("🔍 Phân tích tình trạng hôm nay",
                                 key=f"btn_analyze_{p['id']}"):
                        with st.spinner("AI đang phân tích..."):
                            try:
                                current_logs  = " | ".join([l["c"] for l in p.get("logs", [])])
                                warnings_list = weather.get("agri_warnings", [])
                                dp            = fetch_disease_pressure(lat, lon)
                                vpd_info      = (
                                    f"VPD: {weather.get('vpd','?')} kPa "
                                    f"({weather.get('vpd_status',{}).get('label','')})"
                                )
                                res = model.generate_content(
                                    f"""Bạn là chuyên gia nông nghiệp hữu cơ thực chiến. Trả lời BẰNG TIẾNG VIỆT.

=== THÔNG TIN CÂY ===
- Loại cây: {crop_type} | Tuổi: {age} ngày
- Dự kiến thu hoạch: {p.get('date_harvest', 'Chưa có')}

=== THỜI TIẾT & MÔI TRƯỜNG ===
{safe_weather_str(weather)} | {vpd_info}
Cảnh báo: {', '.join(warnings_list) if warnings_list else 'Không có'}
Áp lực bệnh 48h: {dp.get('level','?').upper()} - {dp.get('hours_risk',0)}h nguy hiểm

=== NHẬT KÝ GẦN NHẤT ===
{current_logs if current_logs else "Chưa có nhật ký"}

### 🌡️ ĐÁNH GIÁ TÌNH TRẠNG HIỆN TẠI
### 💊 PHÂN BÓN CẦN BỔ SUNG NGAY
| Loại phân | Liều lượng | Cách bón | Thời điểm |
|-----------|-----------|----------|-----------|
### 🛡️ PHÒNG TRỊ SÂU BỆNH (có tính đến áp lực bệnh 48h)
| Đối tượng | Dấu hiệu | Xử lý sinh học | Xử lý hóa học |
|-----------|----------|----------------|---------------|
### 📅 LỊCH 7 NGÀY TỚI
| Ngày | Việc cần làm | Lưu ý |
|------|-------------|-------|
### ⚡ HÀNH ĐỘNG NGAY HÔM NAY
Liệt kê đúng 3 việc quan trọng nhất, mỗi việc 1 dòng.
QUAN TRỌNG: Toàn bộ response tối đa 400 từ. Ngắn gọn.""",
                                    request_options={"timeout": 60}
                                )
                                analyze_text = getattr(res, "text", None)
                                if analyze_text:
                                    p["daily_analysis"] = analyze_text
                                    save_data(data)
                                    st.session_state[f"analyze_view_{p['id']}"] = analyze_text
                                    actions   = []
                                    in_action = False
                                    for line in analyze_text.split("\n"):
                                        if "HÀNH ĐỘNG NGAY HÔM NAY" in line:
                                            in_action = True
                                            continue
                                        if in_action and line.strip().startswith(
                                                ("1.", "2.", "3.", "-", "•")):
                                            clean = re.sub(r"^[\d\.\-•\*\s]+", "",
                                                           line).strip()
                                            if clean:
                                                actions.append(clean)
                                        if in_action and line.startswith("#") \
                                                and "HÀNH ĐỘNG" not in line:
                                            break
                                    if actions:
                                        st.session_state[f"actions_{p['id']}"] = actions[:3]
                                else:
                                    st.warning("AI không trả về kết quả.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    analyze_display = st.session_state.get(
                        f"analyze_view_{p['id']}", p.get("daily_analysis"))
                    if analyze_display:
                        with st.expander("🔍 Kết quả phân tích hôm nay", expanded=True):
                            st.markdown(analyze_display)

                        actions = st.session_state.get(f"actions_{p['id']}", [])
                        if actions:
                            st.markdown("**⚡ Xác nhận hành động hôm nay:**")
                            for idx, action in enumerate(actions):
                                col_act, col_done = st.columns([5, 1])
                                with col_act:
                                    st.markdown(f"`{idx+1}.` {action}")
                                with col_done:
                                    if st.button("✅",
                                                 key=f"done_action_{p['id']}_{idx}"):
                                        p.setdefault("logs", []).append({
                                            "d": datetime.now().strftime("%d/%m %H:%M"),
                                            "c": f"✅ Đã thực hiện: {action[:80]}"
                                        })
                                        remaining = [a for j, a in enumerate(actions)
                                                     if j != idx]
                                        if remaining:
                                            st.session_state[f"actions_{p['id']}"] = remaining
                                        else:
                                            st.session_state.pop(f"actions_{p['id']}", None)
                                        save_data(data)
                                        st.success("Đã ghi vào nhật ký!")
                                        st.rerun()

                    st.divider()

                    # Nút 3: Tối ưu 15 ngày
                    if st.button("🧠 AI: Tối ưu 15 ngày tới",
                                 key=f"btn_opt_{p['id']}"):
                        with st.spinner("Đang tổng hợp lịch sử..."):
                            try:
                                current_logs = " | ".join([l["c"] for l in p.get("logs", [])])
                                past_seasons = get_crop_history(data, crop_type)
                                season_ctx   = build_season_context(past_seasons)
                                forecast     = fetch_forecast_7day(lat, lon)
                                forecast_str = " | ".join([
                                    f"{fmt_date(d['date'])}: {d['desc']}, "
                                    f"{d['temp_max']:.0f}°C, ẩm {d['hum_max']:.0f}%, "
                                    f"{RISK_COLOR.get(d['risk'],'')} rủi ro"
                                    for d in forecast
                                ])
                                res = model.generate_content(
                                    f"""Bạn là chuyên gia nông nghiệp hữu cơ cấp cao. Trả lời BẰNG TIẾNG VIỆT.

=== CÂY HIỆN TẠI ===
- Loại: {crop_type} | Tuổi: {age} ngày | Thu hoạch: {p.get('date_harvest', 'Chưa có')}
- Thời tiết: {safe_weather_str(weather)}
- VPD: {weather.get('vpd','?')} kPa ({weather.get('vpd_status',{}).get('label','')})
- Nhật ký: {current_logs if current_logs else "Chưa có"}

=== DỰ BÁO 7 NGÀY TỚI ===
{forecast_str}

=== {len(past_seasons)} VỤ TRƯỚC ===
{season_ctx}

### 📊 PHÂN TÍCH GIAI ĐOẠN SINH TRƯỞNG
### 📊 HỌC TỪ VỤ TRƯỚC
### 🌿 DINH DƯỠNG (có tính đến dự báo thời tiết và VPD)
### 🛡️ BẢO VỆ THỰC VẬT (ưu tiên phòng ngừa dựa trên dự báo)
### 🔧 ĐIỀU CHỈNH TỪ NHẬT KÝ
### 📅 LỊCH 15 NGÀY
| Ngày  | Giai đoạn | Việc cần làm | Lưu ý thời tiết |
|-------|-----------|-------------|-----------------|
| 1-5   | ...       | ...         | ...             |
| 6-10  | ...       | ...         | ...             |
| 11-15 | ...       | ...         | ...             |""",
                                    request_options={"timeout": 60}
                                )
                                recipe_text = getattr(res, "text", None)
                                if recipe_text:
                                    p["optimized_recipe"] = recipe_text
                                    save_data(data)
                                    st.session_state[f"st_view_{p['id']}"] = recipe_text
                                else:
                                    st.warning("AI không trả về kết quả.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    plan_display = st.session_state.get(
                        f"st_view_{p['id']}", p.get("optimized_recipe"))
                    if plan_display:
                        with st.expander("📍 Xem quy trình tối ưu", expanded=False):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chưa có quy trình tối ưu. Hãy nhấn nút AI.")

                    st.divider()
                    render_three_way_match(p, crop_type, age)

                with col_action:
                    st.caption("⚙️ Thao tác")
                    with st.popover("🗑️ Kết thúc vụ"):
                        st.warning(f"Kết thúc vụ **{p['name']}**?")
                        st.caption("Nhật ký & quy trình sẽ được lưu để AI học vụ sau.")
                        if st.button("✔️ Xác nhận",
                                     key=f"btn_del_{p['id']}", type="primary"):
                            data = archive_and_delete_plant(data, p["id"])
                            st.rerun()
                    if weather.get("temp") is not None:
                        st.metric("🌡️", f"{weather['temp']}°C")
                        st.metric("💧", f"{weather['hum']}%")
                        if weather.get("wind") is not None:
                            st.metric("💨", f"{weather['wind']} km/h")
                    dp        = fetch_disease_pressure(lat, lon)
                    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
                    st.metric("🦠 Bệnh 48h", f"{risk_icon} {dp.get('score',0)}/100")

# =============================================================
# 🩺 BÁC SĨ AI & CAMERA
# =============================================================

elif menu == "🩺 Bác sĩ AI & Camera":
    back_button()
    st.title("🩺 Bác sĩ AI Thực địa")

    st.info(
        "💡 **Quy trình:** Chụp ảnh → AI tự nhận diện cây & phân tích "
        "kết hợp thời tiết Meteo + Áp lực bệnh 48h → Chẩn đoán & Kê đơn ngay.\n\n"
        "**Mẹo chụp ảnh:** Đủ ánh sáng | Cận cảnh vết bệnh | "
        "Để phần lá lành trong khung để AI đối chiếu."
    )

    gps_lat = st.session_state["gps_lat"]
    gps_lon = st.session_state["gps_lon"]
    w       = fetch_meteo_direct(gps_lat, gps_lon)
    dp      = fetch_disease_pressure(gps_lat, gps_lon)

    if w["temp"] is not None:
        st.sidebar.metric("🌡️ Nhiệt độ", f"{w['temp']}°C")
        st.sidebar.metric("💧 Độ ẩm",    f"{w['hum']}%")
        if w["wind"] is not None:
            st.sidebar.metric("💨 Gió",  f"{w['wind']} km/h")
        st.sidebar.caption(f"🌤️ {w.get('desc', '')}")
    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
    st.sidebar.metric("🦠 Áp lực bệnh 48h",
                      f"{risk_icon} {dp.get('level','?').upper()}",
                      f"Score: {dp.get('score',0)}/100")

    # Danh sach cay de AI doi chieu — KHONG can chon truoc
    all_plants = data.get("plants", [])
    if all_plants:
        plants_detail = []
        for pl in all_plants:
            try:
                pd_ = datetime.strptime(pl["date"], "%Y-%m-%d")
                age_days = max((datetime.now() - pd_).days, 0)
            except (ValueError, KeyError):
                age_days = 0
            recent_logs = " | ".join([l["c"] for l in pl.get("logs", [])[-3:]])
            parts_      = pl["name"].split("|", 1)
            crop_name_  = parts_[1].strip() if len(parts_) > 1 else parts_[0].strip()
            plants_detail.append(
                f"- {crop_name_} ({pl['name']}): {age_days} ngày tuổi"
                + (f", nhật ký: {recent_logs}" if recent_logs else "")
            )
        plants_detail_str = "\n".join(plants_detail)
    else:
        plants_detail_str = "Chưa có cây nào trong vườn (AI vẫn chẩn đoán bình thường)."

    img_file = st.camera_input("📸 Chụp ảnh cây cần chẩn đoán — không cần chọn cây trước")

    if img_file:
        image = Image.open(img_file)
        st.image(image, caption="Ảnh thực địa", width=500)

        if st.button("🚀 Phân tích & Kê đơn điều trị",
                     type="primary", key="btn_cam_ai"):

            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
            img_bytes = buf.getvalue()

            if w["temp"] is not None:
                weather_ctx = (
                    f"Nhiệt độ: {w['temp']}°C | Độ ẩm: {w['hum']}% | "
                    f"Gió: {w.get('wind','?')} km/h | {w.get('desc','')}"
                )
            else:
                weather_ctx = "Không có dữ liệu thời tiết."

            agri_warns = weather.get("agri_warnings", [])
            dp_summary = (
                f"Áp lực bệnh 48h: {dp.get('level','?').upper()} "
                f"(score {dp.get('score',0)}/100, "
                f"{dp.get('hours_risk',0)}h nguy hiểm, "
                f"cao điểm lúc {dp.get('peak_time','?')})"
            )

            full_prompt = f"""
Bạn là Bác sĩ cây trồng chuyên nghiệp với 20 năm kinh nghiệm thực địa tại Đông Nam Á.
Người nông dân vừa chụp ảnh và cần giúp đỡ NGAY LẬP TỨC.
Dù cây trong ảnh là cây gì, bạn VẪN PHẢI chẩn đoán và đưa ra hướng xử lý cụ thể.

=== VƯỜN HIỆN TẠI (để tham khảo và đối chiếu) ===
{plants_detail_str}

=== THỜI TIẾT THỰC ĐỊA (GPS: {gps_lat:.4f}, {gps_lon:.4f}) ===
{weather_ctx}
{dp_summary}
Cảnh báo nông nghiệp: {', '.join(agri_warns) if agri_warns else 'Không có'}

Nhiệm vụ — nhìn vào ảnh và trả lời NGAY, BẰNG TIẾNG VIỆT:

### 🌿 1. NHẬN DIỆN CÂY
- Tên cây (tên thường gọi + tên khoa học nếu biết).
- Nếu trùng với cây trong vườn → ghi rõ tên định danh và số ngày tuổi.
- Nếu KHÔNG có trong vườn → vẫn nhận diện bình thường và ghi:
  "⚠️ Cây này chưa có trong danh sách vườn — chẩn đoán vẫn đầy đủ bên dưới"

### 🦠 2. CHẨN ĐOÁN VẤN ĐỀ
Phân tích ảnh và xác định TẤT CẢ vấn đề đang thấy:

**Bệnh (nếu có):**
- Tên bệnh + tác nhân: Nấm / Vi khuẩn / Virus
- Dấu hiệu nhận biết từ ảnh (màu sắc, hình dạng, vị trí)
- Mức độ: [Mới xuất hiện / Đang lan rộng / Nghiêm trọng]

**Sâu hại (nếu có):**
- Tên sâu/côn trùng + đặc điểm nhận dạng
- Kiểu gây hại: [Chích hút / Gặm nhấm / Đục thân / Cuộn lá]
- Mức độ thiệt hại hiện tại

**Dinh dưỡng (nếu có dấu hiệu):**
- Triệu chứng nhìn thấy trong ảnh
- Chẩn đoán cụ thể:
  * Vàng lá toàn bộ → thiếu Đạm (N)
  * Vàng giữa gân xanh → thiếu Magie (Mg) hoặc Sắt (Fe)
  * Lá đỏ tím → thiếu Lân (P)
  * Mép lá cháy nâu → thiếu Kali (K)
  * Chồi non chết, biến dạng → thiếu Canxi (Ca) hoặc Bo (B)
  * Lá xanh đậm bất thường → thừa Đạm (N)

**Nếu cây trông bình thường:**
- Ghi: "✅ Cây trông khỏe mạnh, không phát hiện vấn đề rõ ràng"
- Vẫn đưa ra lời khuyên phòng ngừa dựa trên thời tiết hiện tại

### ⚡ 3. LÀM NGAY BÂY GIỜ (trong 24h)
2-3 bước cụ thể, người nông dân làm được ngay:
- Bước 1: ...
- Bước 2: ...
- Bước 3: ...

### 💊 4. THUỐC & CÁCH DÙNG
| Loại | Tên sản phẩm | Liều lượng | Cách dùng |
|------|-------------|------------|-----------|
| 🌿 Sinh học (ưu tiên) | ... | ... | ... |
| ⚗️ Hóa học (khi nặng) | ... | ... | ... |
| 🧪 Dinh dưỡng bổ sung | ... | ... | ... |

### 🌧️ 5. ẢNH HƯỞNG THỜI TIẾT 48H TỚI
Với {weather_ctx} và {dp_summary},
vấn đề này sẽ diễn biến thế nào? Cần làm gì TRƯỚC khi thời tiết thay đổi?

### 📅 6. LỊCH THEO DÕI 7 NGÀY
| Ngày | Việc cần làm | Dấu hiệu cần chú ý |
|------|-------------|-------------------|
| 1-2  | ...         | ...               |
| 3-4  | ...         | ...               |
| 5-7  | ...         | ...               |

### 📈 7. KẾT LUẬN
- Mức độ nguy hiểm: [🟢 Thấp / 🟡 Trung bình / 🔴 Cao / ⛔ Khẩn cấp]
- Nguy cơ lây lan sang cây khác trong vườn: [Thấp / Cao — lý do]
- 1 câu tóm tắt quan trọng nhất cần nhớ.

Ngôn ngữ: NGẮN GỌN, dễ hiểu, như đang nói chuyện trực tiếp với nông dân.
Tuyệt đối KHÔNG nói "tôi không thể xác định" — hãy đưa ra chẩn đoán tốt nhất có thể.
"""

            with st.spinner("🔬 Bác sĩ AI đang phân tích ảnh và dữ liệu thực địa..."):
                try:
                    img_part = {"mime_type": "image/jpeg", "data": img_bytes}
                    res      = model.generate_content(
                        [full_prompt, img_part],
                        request_options={"timeout": 60}
                    )
                    result = getattr(res, "text", None)
                    if result:
                        matched_plant = None
                        for pl in all_plants:
                            parts_     = pl["name"].split("|", 1)
                            crop_name_ = (parts_[1].strip() if len(parts_) > 1
                                          else parts_[0].strip())
                            if crop_name_.lower() in result.lower():
                                matched_plant = pl
                                break
                        st.session_state["last_diagnosis"] = {
                            "result":    result,
                            "plant":     matched_plant,
                            "weather":   w,
                            "in_garden": matched_plant is not None,
                        }
                    else:
                        st.warning("⚠️ AI không phản hồi. Vui lòng thử lại.")
                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")
                    st.info("Kiểm tra lại kết nối mạng hoặc GEMINI_API_KEY.")

    # Ket qua — NGOAI if img_file de khong mat khi chup lai
    diag = st.session_state.get("last_diagnosis")
    if diag:
        st.markdown("---")
        st.subheader("🔬 Kết quả chẩn đoán")
        st.markdown(diag["result"])
        st.markdown("---")

        if diag.get("in_garden") and diag.get("plant"):
            plant_name = diag["plant"]["name"]
            st.success(f"🎯 AI nhận diện khớp với vườn: **{plant_name}**")
            col_save, col_done = st.columns([3, 2])
            with col_save:
                if st.button(f"💾 Lưu vào nhật ký '{plant_name}'",
                             key="btn_save_diag"):
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
            with col_done:
                if st.button("✅ Đã xử lý xong, lưu & đóng",
                             key="btn_done_diag", type="primary"):
                    for p in data["plants"]:
                        if p["id"] == diag["plant"]["id"]:
                            p.setdefault("logs", []).append({
                                "d": datetime.now().strftime("%d/%m %H:%M"),
                                "c": "✅ Đã xử lý bệnh theo chỉ dẫn Bác sĩ AI."
                            })
                            break
                    save_data(data)
                    del st.session_state["last_diagnosis"]
                    st.success("Đã ghi nhật ký hoàn tất!")
                    st.rerun()

        else:
            st.info("🌿 Cây này chưa có trong danh sách vườn — chẩn đoán vẫn đầy đủ ở trên.")
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                if st.button("➕ Thêm cây này vào vườn", key="btn_add_new_plant"):
                    st.session_state["show_add_plant"] = True

            with col_b:
                if all_plants:
                    manual_plant = st.selectbox(
                        "Hoặc lưu vào cây có sẵn:",
                        all_plants,
                        format_func=lambda x: x["name"],
                        key="sb_manual_plant"
                    )
                    if st.button("💾 Lưu vào cây này", key="btn_save_manual"):
                        summary = diag["result"][:120].rsplit(" ", 1)[0] + "..."
                        for p in data["plants"]:
                            if p["id"] == manual_plant["id"]:
                                p.setdefault("logs", []).append({
                                    "d": datetime.now().strftime("%d/%m %H:%M"),
                                    "c": f"🩺 AI Chẩn đoán: {summary}"
                                })
                                break
                        save_data(data)
                        del st.session_state["last_diagnosis"]
                        st.success(f"✅ Đã lưu vào **{manual_plant['name']}**!")
                        st.rerun()

            with col_c:
                if st.button("🚫 Không lưu, chỉ xem", key="btn_discard_diag"):
                    del st.session_state["last_diagnosis"]
                    st.rerun()

            if st.session_state.get("show_add_plant"):
                with st.form("form_add_from_camera"):
                    st.markdown("#### ➕ Thêm cây mới từ chẩn đoán")
                    new_name = st.text_input(
                        "Tên định danh vụ",
                        placeholder="Ví dụ: Ớt sừng - Lứa 02"
                    )
                    new_date  = st.date_input("Ngày trồng xuống đất",
                                               value=datetime.now())
                    submitted = st.form_submit_button("🚀 Thêm vào vườn")
                    if submitted and new_name.strip():
                        data = add_plant(
                            data, new_name,
                            new_date.strftime("%Y-%m-%d"),
                            extra={
                                "date_seed_soak": None,
                                "date_seedling":  None,
                                "date_harvest":   None,
                            }
                        )
                        summary = diag["result"][:120].rsplit(" ", 1)[0] + "..."
                        data["plants"][-1].setdefault("logs", []).append({
                            "d": datetime.now().strftime("%d/%m %H:%M"),
                            "c": f"🩺 AI Chẩn đoán lần đầu: {summary}"
                        })
                        save_data(data)
                        del st.session_state["last_diagnosis"]
                        st.session_state.pop("show_add_plant", None)
                        st.success(f"✅ Đã thêm **{new_name}** và lưu chẩn đoán!")
                        st.rerun()

# =============================================================
# 💬 TRỢ LÝ KỸ THUẬT
# =============================================================

elif menu == "💬 Trợ lý Kỹ thuật":
    back_button()
    st.title("💬 Trợ lý Kỹ thuật Nông nghiệp")

    city      = weather.get("city", "...")
    temp_now  = weather.get("temp", "?")
    hum_now   = weather.get("hum",  "?")
    wind_now  = weather.get("wind", "?")
    desc_now  = weather.get("desc", "")
    vpd_now   = weather.get("vpd")
    vpd_label = weather.get("vpd_status", {}).get("label", "")
    dp        = fetch_disease_pressure(lat, lon)
    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")

    st.caption(
        f"📍 {city} | {temp_now}°C — {hum_now}% ẩm — Gió {wind_now} km/h — {desc_now}"
        + (f" | VPD {vpd_now} kPa ({vpd_label})" if vpd_now else "")
        + f" | 🦠 Bệnh 48h: {risk_icon} {dp.get('level','?').upper()}"
    )

    # Chi giu 50 tin nhan gan nhat
    chat_history = data.get("chat_history", [])[-50:]
    for chat in chat_history:
        with st.chat_message("user"):
            st.write(chat["user"])
        with st.chat_message("assistant"):
            st.markdown(chat["ai"])

    if prompt := st.chat_input("Hỏi AI về kỹ thuật vườn, phân bón, sâu bệnh..."):
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("🤖 AI đang phân tích dữ liệu..."):
            try:
                # Tổng hợp nhật ký tất cả cây trong vườn
                plant_history = []
                for pl in data.get("plants", []):
                    try:
                        pd_ = datetime.strptime(pl["date"], "%Y-%m-%d")
                        age_days = max((datetime.now() - pd_).days, 0)
                    except (ValueError, KeyError):
                        age_days = 0

                    parts_     = pl["name"].split("|", 1)
                    crop_name_ = parts_[1].strip() if len(parts_) > 1 else parts_[0].strip()

                    recent_logs = " → ".join([
                        f"{l['d']}: {l['c']}" for l in pl.get("logs", [])[-5:]
                    ])

                    plant_history.append(
                        f"• {crop_name_} ({age_days} ngày tuổi)"
                        + (f"\n  Nhật ký gần nhất: {recent_logs}" if recent_logs
                           else "\n  Nhật ký: Chưa có")
                        + (f"\n  Dự kiến thu hoạch: {pl['date_harvest']}"
                           if pl.get("date_harvest") else "")
                    )

                plant_history_str = (
                    "\n".join(plant_history)
                    if plant_history
                    else "Chưa có cây nào trong vườn."
                )

                w_ctx = (
                    f"Nhiệt độ {temp_now}°C, Độ ẩm {hum_now}%, "
                    f"Gió {wind_now} km/h, {desc_now}"
                    + (f", VPD {vpd_now} kPa ({vpd_label})" if vpd_now else "")
                    + f". Áp lực bệnh 48h: {dp.get('level','?').upper()} "
                    f"(score {dp.get('score',0)}/100)"
                )

                full_prompt = f"""
Bạn là Chuyên gia Nông nghiệp Công nghệ cao, đang tư vấn trực tiếp cho chủ vườn.
Trả lời BẰNG TIẾNG VIỆT, ngắn gọn và sát thực tế.

=== MÔI TRƯỜNG HIỆN TẠI tại {city} ===
{w_ctx}

=== TÌNH TRẠNG CÁC CÂY TRONG VƯỜN ===
{plant_history_str}

=== CÂU HỎI CỦA NÔNG DÂN ===
{prompt}

Yêu cầu khi trả lời:
- Nếu câu hỏi liên quan đến cây cụ thể trong vườn → đối chiếu với nhật ký
  của cây đó để trả lời SÁT THỰC TẾ, không trả lời chung chung.
- Nếu nhật ký có dấu hiệu bất thường liên quan → chủ động đề cập và cảnh báo.
- Ưu tiên giải pháp hữu cơ/sinh học, chỉ đề xuất hóa học khi thực sự cần.
- Có tính đến VPD và áp lực bệnh 48h khi tư vấn tưới tiêu và phòng bệnh.
- Dùng Markdown (###, **, -) để trình bày rõ ràng.
QUAN TRỌNG: Tối đa 300 từ. Đi thẳng vào vấn đề."""
                response = model.generate_content(
                    full_prompt,
                    request_options={"timeout": 60}
                )
                ai_res = (
                    response.text if hasattr(response, "text")
                    else "⚠️ AI không thể trả lời câu hỏi này."
                )

                with st.chat_message("assistant"):
                    st.markdown(ai_res)

                add_chat(data, prompt, ai_res)
                if len(data.get("chat_history", [])) > 50:
                    data["chat_history"] = data["chat_history"][-50:]
                save_data(data)
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Lỗi kết nối AI: {e}")
                st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets.")
