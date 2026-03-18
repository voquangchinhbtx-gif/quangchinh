# -*- coding: utf-8 -*-
"""
app.py - GREEN FARM
Chạy: streamlit run app.py
"""

import io
import re
import socket
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
    get_forecast_7day, get_disease_pressure_7day
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
                for l in logs[-5:]
            ]
            lines.append("Nhật ký: " + " | ".join(log_texts))
        recipe = s.get("recipe", "")
        if recipe:
            lines.append(f"Quy trình vụ đó: {recipe[:200]}...")
    return "\n".join(lines)


def get_weather_safe() -> dict:
    cached = st.session_state.get("last_weather_cache")
    if cached:
        cached = dict(cached)
        cached["desc"] = "📵 Offline — " + cached.get("desc", "")
        return cached
    return {
        "temp": None, "hum": None, "wind": None,
        "rain": None, "desc": "Đang tải...",
        "city": "Đang xác định...",
        "lat": DEFAULT_LAT, "lon": DEFAULT_LON,
        "vpd": None, "vpd_status": {},
        "agri_warnings": []
    }


def fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")
    except Exception:
        return d


def get_current_stage(p: dict) -> dict:
    """Xác định giai đoạn hiện tại dựa trên các mốc thời gian đã có."""
    if p.get("date"):
        try:
            age = max((datetime.now() - datetime.strptime(p["date"], "%Y-%m-%d")).days, 0)
        except (ValueError, KeyError):
            age = 0
        return {"stage": "transplant", "label": "🌱 Đã trồng xuống đất",
                "age": age, "emoji": "🌱", "next": None}

    elif p.get("date_seedling"):
        try:
            age = max((datetime.now() - datetime.strptime(p["date_seedling"], "%Y-%m-%d")).days, 0)
        except (ValueError, KeyError):
            age = 0
        return {"stage": "seedling", "label": "🌿 Đang gieo ươm",
                "age": age, "emoji": "🌿", "next": "🌱 Trồng xuống đất"}

    elif p.get("date_seed_soak"):
        try:
            age = max((datetime.now() - datetime.strptime(p["date_seed_soak"], "%Y-%m-%d")).days, 0)
        except (ValueError, KeyError):
            age = 0
        return {"stage": "seed_soak", "label": "🫧 Đang ủ hạt",
                "age": age, "emoji": "🫧", "next": "🌿 Gieo ươm"}

    return {"stage": "unknown", "label": "Chưa xác định",
            "age": 0, "emoji": "❓", "next": None}

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
    try:
        loc = get_geolocation()
        if loc and isinstance(loc, dict) and "coords" in loc:
            new_lat = float(loc["coords"]["latitude"])
            new_lon = float(loc["coords"]["longitude"])
            if abs(new_lat) > 0.01 or abs(new_lon) > 0.01:
                st.session_state["gps_lat"]      = new_lat
                st.session_state["gps_lon"]      = new_lon
                st.session_state["gps_resolved"] = True
    except Exception:
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
    return get_disease_pressure_7day(lat, lon)


# =============================================================
# TẢI DỮ LIỆU
# =============================================================

data    = load_data()
lat     = st.session_state["gps_lat"]
lon     = st.session_state["gps_lon"]
_w      = fetch_weather_data(lat, lon)
if _w and _w.get("temp") is not None:
    st.session_state["last_weather_cache"] = _w
    weather = _w
else:
    weather = get_weather_safe()

# =============================================================
# SIDEBAR
# =============================================================

with st.sidebar:
    st.title("🌿 GREEN FARM")
    st.caption(f"📍 {weather.get('city', '...')}")
    gps_source = "📡 GPS thực" if st.session_state["gps_resolved"] else "📌 Mặc định"
    st.caption(f"{gps_source}: {lat:.4f}, {lon:.4f}")

    # Dropdown chon thanh pho phong khi GPS fail
    with st.expander("📍 Chỉnh vị trí", expanded=not st.session_state["gps_resolved"]):
        city_presets = {
            "📌 Kim Long, Huế":     (16.45780, 107.56150),
            "🏙️ Hà Nội":           (21.0285,  105.8542),
            "🏙️ TP. Hồ Chí Minh":  (10.7769,  106.7009),
            "🏙️ Đà Nẵng":          (16.0544,  108.2022),
            "🏙️ Cần Thơ":          (10.0452,  105.7469),
            "🏙️ Nha Trang":        (12.2388,  109.1967),
            "🏙️ Đà Lạt":           (11.9465,  108.4419),
            "✏️ Nhập tọa độ tay":   None,
        }
        selected_city = st.selectbox("Chọn thành phố:",
                                     list(city_presets.keys()),
                                     key="city_preset")
        if city_presets[selected_city] is not None:
            if st.button("✅ Dùng vị trí này", key="btn_use_preset"):
                preset_lat, preset_lon = city_presets[selected_city]
                st.session_state["gps_lat"]      = preset_lat
                st.session_state["gps_lon"]      = preset_lon
                st.session_state["gps_resolved"] = True
                st.cache_data.clear()
                st.rerun()
        else:
            manual_lat = st.number_input("Vĩ độ:", value=float(lat), format="%.4f", key="manual_lat")
            manual_lon = st.number_input("Kinh độ:", value=float(lon), format="%.4f", key="manual_lon")
            if st.button("✅ Lưu tọa độ", key="btn_save_coords"):
                st.session_state["gps_lat"]      = manual_lat
                st.session_state["gps_lon"]      = manual_lon
                st.session_state["gps_resolved"] = True
                st.cache_data.clear()
                st.rerun()
        if st.button("🔄 Reset mặc định", key="btn_reset_gps"):
            st.session_state["gps_lat"]      = DEFAULT_LAT
            st.session_state["gps_lon"]      = DEFAULT_LON
            st.session_state["gps_resolved"] = False
            st.cache_data.clear()
            st.rerun()

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
    st.markdown("### 🗓️ Dự báo 7 ngày")
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
                f"**{label}**\n\n{icon}\n\n"
                f"↑{day['temp_max']:.0f}° ↓{day['temp_min']:.0f}°\n\n"
                f"💧{day['hum_max']:.0f}%"
                + (f"\n\n🌧️{day['rain']:.1f}mm" if day["rain"] > 0 else "")
                + f"\n\n_{day['desc'][:12]}_"
            )
            if risk == "critical":   st.error(content)
            elif risk == "high":     st.warning(content)
            elif risk == "medium":   st.info(content)
            else:                    st.success(content)

    st.caption("🟢 An toàn  🟡 Theo dõi  🔴 Nguy cơ  ⛔ Nguy hiểm")

# =============================================================
# COMPONENT: ÁP LỰC BỆNH 7 ngày
# =============================================================

def render_disease_pressure_7day(lat: float, lon: float):
    st.markdown("### 🦠 Áp lực bệnh 7 ngày")
    dp = fetch_disease_pressure(lat, lon)

    level      = dp.get("level", "unknown")
    score      = dp.get("score", 0)
    hours_risk = dp.get("hours_risk", 0)
    peak_time  = dp.get("peak_time", "")
    warnings   = dp.get("warnings", [])

    col1, col2, col3 = st.columns(3)
    icon = RISK_COLOR.get(level, "⚪")
    col1.metric("Mức độ rủi ro", f"{icon} {level.upper()}", f"Score: {score}/100")
    col2.metric("Giờ nguy hiểm", f"{hours_risk}h / 7 ngày")
    col3.metric("Cao điểm",      peak_time if peak_time else "N/A")
    st.progress(min(score, 100))

    for w in warnings:
        if level in ("critical", "high"):   st.error(w)
        elif level == "medium":             st.warning(w)
        else:                               st.success(w)

    hourly = dp.get("hourly", [])
    if hourly:
        df = pd.DataFrame(hourly)
        df["color"] = df["risk"].map({
            "high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"
        })
        df_display = df[df.index % 2 == 0].copy()
        chart = (
            alt.Chart(df_display)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("time:N", title="Giờ", sort=None,
                        axis=alt.Axis(labelAngle=-45, labelFontSize=10)),
                y=alt.Y("score:Q", title="Điểm rủi ro (0-10)",
                        scale=alt.Scale(domain=[0, 10])),
                color=alt.Color("color:N", scale=None, legend=None),
                tooltip=[
                    alt.Tooltip("time:N",  title="Giờ"),
                    alt.Tooltip("temp:Q",  title="Nhiệt độ °C"),
                    alt.Tooltip("hum:Q",   title="Độ ẩm %"),
                    alt.Tooltip("score:Q", title="Điểm rủi ro"),
                ]
            )
            .properties(
                title=alt.TitleParams("⏱️ Diễn biến áp lực bệnh 7 ngày",
                                      fontSize=13, anchor="start"),
                height=200
            )
        )
        threshold = (
            alt.Chart(pd.DataFrame({"y": [5]}))
            .mark_rule(color="#e74c3c", strokeDash=[4, 4], size=1.5)
            .encode(y="y:Q")
        )
        st.altair_chart(chart + threshold, use_container_width=True)
        st.caption("📊 Đường đứt đỏ = ngưỡng cảnh báo")

# =============================================================
# COMPONENT: SO KHỚP 3 BÊN AI
# =============================================================

def render_three_way_match(p: dict, crop_type: str, age: int):
    st.markdown("### 🧠 Bộ não nhắc nhở")

    if st.button("🔄 Phân tích & Nhắc việc", key=f"btn_3way_{p['id']}"):
        current_logs  = " | ".join([l["c"] for l in p.get("logs", [])[-5:]])
        std_recipe    = p.get("standard_recipe", "Chưa có quy trình.")[:300]
        warnings_list = weather.get("agri_warnings", [])
        dp            = fetch_disease_pressure(lat, lon)

        prompt = f"""
Bạn là AI quản lý vườn. Trả lời BẰNG TIẾNG VIỆT, tối đa 150 từ.

Cây: {crop_type} | Tuổi: {age} ngày
Nhật ký: {current_logs if current_logs else "Chưa có"}
Thời tiết: {safe_weather_str(weather)}
Áp lực bệnh: {dp.get('level','?').upper()} (score {dp.get('score',0)}/100)
Quy trình: {std_recipe}

Tìm tối đa 5 việc bị bỏ sót hoặc cần làm ngay.
Format bắt buộc:
VIEC_1: [🚨/⚠️/💡] [tên việc] | [lý do ngắn]
VIEC_2: ...
"""
        with st.spinner("AI đang phân tích..."):
            try:
                res  = model.generate_content(prompt, request_options={"timeout": 30})
                text = getattr(res, "text", "") or ""
                tasks = []
                for line in text.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("VIEC_") and ":" in line:
                        task_text = line.split(":", 1)[1].strip()
                        if task_text:
                            tasks.append(task_text)
                if not tasks:
                    tasks = [l.strip() for l in text.strip().split("\n")
                             if l.strip() and len(l.strip()) > 10][:5]
                if tasks:
                    st.session_state[f"tasks_3way_{p['id']}"] = tasks
                    p["tasks_3way"] = tasks
                    save_data(data)
                    st.rerun()
            except Exception as e:
                st.error(f"Lỗi AI: {e}")

    tasks = st.session_state.get(f"tasks_3way_{p['id']}", p.get("tasks_3way", []))
    if tasks:
        st.markdown("---")
        st.markdown("#### 📋 Việc cần làm")

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

            container = (st.error   if "🚨" in task_name else
                         st.warning if "⚠️" in task_name else st.info)

            col_main, col_btn = st.columns([5, 1])
            with col_main:
                container(f"**{task_name}**\n\n_{reason}_" if reason
                          else f"**{task_name}**")
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅", key=f"done_3way_{p['id']}_{idx}",
                             use_container_width=True):
                    p.setdefault("logs", []).append({
                        "d": datetime.now().strftime("%d/%m %H:%M"),
                        "c": f"✅ Đã thực hiện (AI nhắc): {task_name[:80]}"
                    })
                    remaining = [t for j, t in enumerate(tasks) if j != idx]
                    st.session_state[f"tasks_3way_{p['id']}"] = remaining
                    p["tasks_3way"] = remaining
                    save_data(data)
                    st.rerun()

        if st.button("🎉 Hoàn thành tất cả",
                     key=f"done_all_{p['id']}",
                     type="primary", use_container_width=True):
            for task in tasks:
                p.setdefault("logs", []).append({
                    "d": datetime.now().strftime("%d/%m %H:%M"),
                    "c": f"✅ Đã thực hiện: {task.split('|')[0].strip()[:80]}"
                })
            st.session_state.pop(f"tasks_3way_{p['id']}", None)
            p["tasks_3way"] = []
            save_data(data)
            st.success("🎉 Hoàn thành tất cả!")
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
            wind_delta = ("⛔ Rất mạnh" if wind_val >= 40
                          else "⚠️ Vừa" if wind_val >= 20 else "✅ Nhẹ")
            st.metric("💨 Gió", f"{wind_val} km/h", wind_delta)

        vpd        = weather.get("vpd")
        vpd_status = weather.get("vpd_status", {})
        if vpd is not None:
            st.markdown(
                f"### 💨 VPD: `{vpd:.2f} kPa` — {vpd_status.get('label','')}"
            )
            if vpd_status.get("warning"):
                if vpd_status["level"] in ("danger_low", "danger_high"):
                    st.error(vpd_status["warning"])
                else:
                    st.warning(vpd_status["warning"])

        warnings = weather.get("agri_warnings", [])
        if warnings:
            st.markdown("### 🚨 Cảnh báo Nông nghiệp")
            for w in warnings:
                st.info(w)

        st.divider()
        render_forecast_7day(lat, lon)
        st.divider()
        render_disease_pressure_7day(lat, lon)
    else:
        st.info("⏳ Đang tải dữ liệu thời tiết...")

# =============================================================
# 🌱 QUẢN LÝ CÂY TRỒNG
# =============================================================

elif menu == "🌱 Quản lý Cây trồng":
    back_button()
    st.title("🌱 Quản lý Vườn & Hệ thống Tối ưu AI")

    with st.expander("⚙️ Thiết lập & Quản lý danh sách cây", expanded=False):
        tab_add, tab_edit = st.tabs(["➕ Thêm cây mới", "✏️ Chỉnh sửa"])

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
            st.caption("💡 Chỉ tick những mốc đã xảy ra — cập nhật sau khi có.")

            has_seed_soak = st.checkbox("🫧 Đã ủ hạt", key="has_seed_soak")
            date_seed_soak = None
            if has_seed_soak:
                date_seed_soak = st.date_input("Ngày ủ hạt",
                                               value=datetime.now(),
                                               key="date_seed_soak")

            has_seedling = st.checkbox("🌿 Đã gieo ươm", key="has_seedling",
                                       disabled=not has_seed_soak)
            date_seedling = None
            if has_seedling:
                date_seedling = st.date_input("Ngày gieo ươm",
                                              value=datetime.now(),
                                              key="date_seedling")

            has_transplant = st.checkbox("🌱 Đã trồng xuống đất",
                                         key="has_transplant",
                                         disabled=not has_seedling)
            date_transplant = None
            if has_transplant:
                date_transplant = st.date_input("Ngày trồng xuống đất",
                                                value=datetime.now(),
                                                key="date_transplant")

            if has_seed_soak:
                stage_now = ("🌱 Đã trồng" if has_transplant
                             else "🌿 Đang ươm" if has_seedling
                             else "🫧 Đang ủ hạt")
                st.info(f"📍 Giai đoạn: **{stage_now}**")
                st.caption("🍅 Ngày thu hoạch do AI tự tính.")

            if st.button("🚀 Khởi tạo vườn", key="btn_init_farm"):
                if name_in.strip() and type_in.strip():
                    if not has_seed_soak:
                        st.warning("Vui lòng tick ít nhất 🫧 Đã ủ hạt.")
                    else:
                        main_date = (
                            date_transplant or date_seedling or date_seed_soak
                        ).strftime("%Y-%m-%d")
                        data = add_plant(
                            data, f"{name_in} | {type_in}",
                            main_date,
                            extra={
                                "date_seed_soak": date_seed_soak.strftime("%Y-%m-%d")
                                                  if date_seed_soak else None,
                                "date_seedling":  date_seedling.strftime("%Y-%m-%d")
                                                  if date_seedling else None,
                                "date_harvest":   None,
                            }
                        )
                        save_data(data)
                        st.success(f"Đã thêm **{name_in}**! Nhấn tạo quy trình để AI tư vấn.")
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
                        val_tr = (datetime.strptime(p_edit["date"], "%Y-%m-%d")
                                  if p_edit.get("date") else datetime.now())
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
                    st.text_input("🍅 Dự kiến thu hoạch",
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
        st.info("🌵 Vườn chưa có cây. Hãy thêm cây mới ở trên.")
    else:
        with st.expander("🦠 Nguy cơ bệnh 7 ngày toàn vườn", expanded=False):
            render_disease_pressure_7day(lat, lon)

        for p in plants_list:
            with st.container(border=True):
                col_info, col_care, col_action = st.columns([1.2, 2.5, 0.8])

                stage_info = get_current_stage(p)
                age        = stage_info["age"]

                with col_info:
                    st.subheader(f"🌿 {p['name']}")
                    st.write(f"{stage_info['emoji']} **{stage_info['label']}**")
                    st.write(f"⏱️ **{age} ngày** kể từ mốc này")

                    if p.get("date_seed_soak"):
                        st.caption(f"🫧 Ủ hạt: {p['date_seed_soak']}")
                    if p.get("date_seedling"):
                        st.caption(f"🌿 Gieo ươm: {p['date_seedling']}")
                    if p.get("date"):
                        st.caption(f"🌱 Trồng: {p['date']}")
                    st.caption(
                        f"🍅 Thu hoạch: {p['date_harvest']}"
                        if p.get("date_harvest") else "🍅 Thu hoạch: Chưa có"
                    )

                    # Nut cap nhat moc tiep theo
                    if stage_info.get("next"):
                        with st.popover(f"📅 Cập nhật: {stage_info['next']}"):
                            if stage_info["stage"] == "seed_soak":
                                new_date = st.date_input("🌿 Ngày gieo ươm",
                                                         value=datetime.now(),
                                                         key=f"upd_seedling_{p['id']}")
                                if st.button("✅ Xác nhận",
                                             key=f"btn_upd_seedling_{p['id']}"):
                                    p["date_seedling"] = new_date.strftime("%Y-%m-%d")
                                    p.pop("recipe_seed_soak", None)
                                    p.pop("recipe_seedling", None)
                                    p.pop("recipe_transplant", None)
                                    p.pop("optimized_recipe", None)
                                    for k in list(st.session_state.keys()):
                                        if str(p['id']) in k and "show_" in k:
                                            del st.session_state[k]
                                    save_data(data)
                                    st.success("✅ Đã cập nhật! AI sẽ tạo quy trình mới.")
                                    st.rerun()
                            elif stage_info["stage"] == "seedling":
                                new_date = st.date_input("🌱 Ngày trồng xuống đất",
                                                         value=datetime.now(),
                                                         key=f"upd_transplant_{p['id']}")
                                if st.button("✅ Xác nhận",
                                             key=f"btn_upd_transplant_{p['id']}"):
                                    p["date"] = new_date.strftime("%Y-%m-%d")
                                    p.pop("recipe_transplant", None)
                                    p.pop("optimized_recipe", None)
                                    for k in list(st.session_state.keys()):
                                        if str(p['id']) in k and "show_transplant" in k:
                                            del st.session_state[k]
                                    save_data(data)
                                    st.success("✅ Đã cập nhật! AI sẽ tạo quy trình mới.")
                                    st.rerun()

                    st.divider()

                    with st.popover("📖 Nhật ký vườn"):
                        st.write(f"📝 **{p['name']}**")
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
                    st.markdown(f"📋 **Quy trình AI cho: {crop_type}**")

                    # ── Nut 1: Tao quy trinh cho TUNG giai doan da co ──
                    stage_labels = {
                        "seed_soak":  "🫧 Ủ hạt",
                        "seedling":   "🌿 Gieo ươm",
                        "transplant": "🌱 Sau trồng",
                    }

                    stages_available = []
                    if p.get("date_seed_soak"):
                        stages_available.append("seed_soak")
                    if p.get("date_seedling"):
                        stages_available.append("seedling")
                    if p.get("date"):
                        stages_available.append("transplant")

                    for stage_key in stages_available:
                        stage_label = stage_labels[stage_key]
                        recipe_key  = f"recipe_{stage_key}"
                        view_key    = f"show_{stage_key}_{p['id']}"
                        has_recipe  = bool(p.get(recipe_key))
                        is_open     = st.session_state.get(view_key, False)

                        col_t, col_b1, col_b2 = st.columns([3, 1, 1])
                        with col_t:
                            st.markdown(f"**📋 {stage_label}**")
                        with col_b1:
                            btn_label = ("🔽 Tạo" if not has_recipe
                                         else ("🔼 Thu" if is_open else "🔽 Xem"))
                            if st.button(btn_label,
                                         key=f"btn_toggle_{stage_key}_{p['id']}",
                                         use_container_width=True):
                                if not has_recipe:
                                    with st.spinner(f"AI đang tạo quy trình {stage_label}..."):
                                        try:
                                            if stage_key == "seed_soak":
                                                stage_prompt = """
### 🫧 CHĂM SÓC HẠT ĐANG Ủ
- Nhiệt độ, độ ẩm cần duy trì
- Dấu hiệu nảy mầm tốt / không tốt
- Thời gian nảy mầm dự kiến

### ⚠️ LỖI THƯỜNG GẶP KHI Ủ HẠT

### 📅 DỰ KIẾN NGÀY GIEO ƯƠM
Ngày gieo ươm dự kiến: YYYY-MM-DD
Tối đa 150 từ."""

                                            elif stage_key == "seedling":
                                                stage_prompt = """
### 🌿 CHĂM SÓC CÂY CON ĐANG ƯƠM
- Ánh sáng, nhiệt độ, tưới nước
- Phân bón giai đoạn ươm

### 🛡️ PHÒNG BỆNH KHI ƯƠM

### 📅 DỰ KIẾN NGÀY TRỒNG XUỐNG ĐẤT
Ngày trồng xuống đất dự kiến: YYYY-MM-DD
Tối đa 150 từ."""

                                            else:
                                                stage_prompt = """
### 🌱 CÂY CON (0-30 ngày)
### 🌿 PHÁT TRIỂN (30-60 ngày)
### 🌸 RA HOA / KẾT TRÁI
### 🍅 THU HOẠCH
### ⚠️ BỆNH THƯỜNG GẶP
| Bệnh | Dấu hiệu | Xử lý sinh học | Xử lý hóa học |
|------|----------|----------------|---------------|

### 📆 DỰ KIẾN NGÀY THU HOẠCH
Ngày thu hoạch dự kiến: YYYY-MM-DD
Tối đa 300 từ."""

                                            res = model.generate_content(
                                                f"""Chuyên gia nông nghiệp hữu cơ. Trả lời BẰNG TIẾNG VIỆT, ngắn gọn.
Cây: {crop_type} | Giai đoạn: {stage_label}
Ủ hạt: {p.get('date_seed_soak','Chưa có')}
Gieo ươm: {p.get('date_seedling','Chưa có')}
Trồng: {p.get('date','Chưa có')}
Thời tiết: {safe_weather_str(weather)}

{stage_prompt}""",
                                                request_options={"timeout": 60}
                                            )
                                            text = getattr(res, "text", None)
                                            if text:
                                                p[recipe_key] = text
                                                for pattern, field in [
                                                    (r"Ngày thu hoạch dự kiến:\s*(\d{4}-\d{2}-\d{2})",       "date_harvest"),
                                                    (r"Ngày trồng xuống đất dự kiến:\s*(\d{4}-\d{2}-\d{2})", "date_transplant_est"),
                                                    (r"Ngày gieo ươm dự kiến:\s*(\d{4}-\d{2}-\d{2})",        "date_seedling_est"),
                                                ]:
                                                    match = re.search(pattern, text)
                                                    if match:
                                                        p[field] = match.group(1)
                                                        break
                                                save_data(data)
                                                st.session_state[view_key] = True
                                                st.rerun()
                                            else:
                                                st.warning("AI không trả về kết quả.")
                                        except Exception as e:
                                            st.error(f"Lỗi AI: {e}")
                                else:
                                    st.session_state[view_key] = not is_open
                                    st.rerun()

                        with col_b2:
                            if has_recipe:
                                if st.button("🔄", key=f"btn_redo_{stage_key}_{p['id']}",
                                             help="Tạo lại quy trình",
                                             use_container_width=True):
                                    p.pop(recipe_key, None)
                                    st.session_state.pop(view_key, None)
                                    save_data(data)
                                    st.rerun()

                        if has_recipe and st.session_state.get(view_key, False):
                            st.markdown(p[recipe_key])

                    st.divider()

                    # ── Nut 2: Phan tich hom nay ──
                    if st.button("🔍 Phân tích hôm nay",
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
                                    f"""Chuyên gia nông nghiệp. Trả lời BẰNG TIẾNG VIỆT, tối đa 200 từ.

Cây: {crop_type} | {stage_info['label']} ({age} ngày)
Thời tiết: {safe_weather_str(weather)} | {vpd_info}
Nguy cơ bệnh: {dp.get('level','?').upper()} - {dp.get('hours_risk',0)}h nguy hiểm
Nhật ký: {current_logs if current_logs else "Chưa có"}

### ĐÁNH GIÁ NHANH
### PHÂN BÓN CẦN BỔ SUNG (nếu có)
### PHÒNG TRỊ SÂU BỆNH (nếu cần)
### 3 VIỆC CẦN LÀM NGAY HÔM NAY""",
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
                                        if "VIỆC CẦN LÀM NGAY" in line:
                                            in_action = True
                                            continue
                                        if in_action and line.strip().startswith(
                                                ("1.", "2.", "3.", "-", "•")):
                                            clean = re.sub(r"^[\d\.\-•\*\s]+", "", line).strip()
                                            if clean:
                                                actions.append(clean)
                                        if in_action and line.startswith("#") \
                                                and "VIỆC" not in line:
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
                        col_t, col_b = st.columns([4, 1])
                        with col_t:
                            st.markdown("**🔍 Phân tích hôm nay**")
                        with col_b:
                            key     = f"show_analyze_{p['id']}"
                            is_open = st.session_state.get(key, True)
                            if st.button("🔼 Thu" if is_open else "🔽 Xem",
                                         key=f"btn_{key}"):
                                st.session_state[key] = not is_open
                                st.rerun()
                        if st.session_state.get(f"show_analyze_{p['id']}", True):
                            st.markdown(analyze_display)
                            actions = st.session_state.get(f"actions_{p['id']}", [])
                            if actions:
                                st.markdown("**⚡ Xác nhận hành động:**")
                                for idx, action in enumerate(actions):
                                    col_act, col_done = st.columns([5, 1])
                                    with col_act:
                                        st.markdown(f"`{idx+1}.` {action}")
                                    with col_done:
                                        if st.button("✅", key=f"done_action_{p['id']}_{idx}"):
                                            p.setdefault("logs", []).append({
                                                "d": datetime.now().strftime("%d/%m %H:%M"),
                                                "c": f"✅ Đã thực hiện: {action[:80]}"
                                            })
                                            remaining = [a for j, a in enumerate(actions) if j != idx]
                                            if remaining:
                                                st.session_state[f"actions_{p['id']}"] = remaining
                                            else:
                                                st.session_state.pop(f"actions_{p['id']}", None)
                                            save_data(data)
                                            st.rerun()

                    st.divider()

                    # ── Nut 3: Toi uu 15 ngay ──
                    if st.button("🧠 Tối ưu 15 ngày tới",
                                 key=f"btn_opt_{p['id']}"):
                        with st.spinner("Đang tổng hợp..."):
                            try:
                                current_logs = " | ".join([l["c"] for l in p.get("logs", [])])
                                past_seasons = get_crop_history(data, crop_type)
                                season_ctx   = build_season_context(past_seasons)
                                forecast     = fetch_forecast_7day(lat, lon)
                                forecast_str = " | ".join([
                                    f"{fmt_date(d['date'])}: {d['desc']}, "
                                    f"{d['temp_max']:.0f}°C, {RISK_COLOR.get(d['risk'],'')} rủi ro"
                                    for d in forecast
                                ])
                                res = model.generate_content(
                                    f"""Chuyên gia nông nghiệp. Trả lời BẰNG TIẾNG VIỆT, tối đa 300 từ.

Cây: {crop_type} | {stage_info['label']} ({age} ngày)
Thu hoạch: {p.get('date_harvest','Chưa có')}
Thời tiết: {safe_weather_str(weather)}
Dự báo 7 ngày: {forecast_str}
Nhật ký: {current_logs if current_logs else "Chưa có"}
Vụ trước: {season_ctx}

### PHÂN TÍCH GIAI ĐOẠN
### DINH DƯỠNG (theo dự báo thời tiết)
### BẢO VỆ THỰC VẬT
### LỊCH 15 NGÀY
| Ngày  | Việc cần làm | Lưu ý |
|-------|-------------|-------|
| 1-5   | ...         | ...   |
| 6-10  | ...         | ...   |
| 11-15 | ...         | ...   |""",
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
                        col_t, col_b = st.columns([4, 1])
                        with col_t:
                            st.markdown("**📍 Quy trình tối ưu 15 ngày**")
                        with col_b:
                            key     = f"show_opt_{p['id']}"
                            is_open = st.session_state.get(key, False)
                            if st.button("🔼 Thu" if is_open else "🔽 Xem",
                                         key=f"btn_{key}"):
                                st.session_state[key] = not is_open
                                st.rerun()
                        if st.session_state.get(f"show_opt_{p['id']}", False):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chưa có quy trình tối ưu.")

                    st.divider()
                    render_three_way_match(p, crop_type, age)

                with col_action:
                    st.caption("⚙️ Thao tác")

                    with st.popover("✅ Kết thúc vụ"):
                        st.warning(f"Kết thúc vụ **{p['name']}**?")
                        st.caption("Nhật ký & quy trình lưu lại để AI học vụ sau.")
                        if st.button("✔️ Xác nhận",
                                     key=f"btn_end_{p['id']}", type="primary"):
                            data = archive_and_delete_plant(data, p["id"])
                            st.rerun()

                    with st.popover("🗑️ Xóa cây"):
                        st.error(f"Xóa **{p['name']}**?")
                        reason = st.radio(
                            "Lý do:",
                            ["🌿 Thêm nhầm", "🦠 Cây bị bệnh/chết", "🌪️ Thiên tai"],
                            key=f"del_reason_{p['id']}"
                        )
                        if reason == "🌿 Thêm nhầm":
                            st.caption("Xóa hoàn toàn, không lưu.")
                            if st.button("🗑️ Xóa luôn",
                                         key=f"btn_del_wrong_{p['id']}",
                                         type="primary"):
                                data["plants"] = [pl for pl in data["plants"]
                                                  if pl["id"] != p["id"]]
                                save_data(data)
                                st.rerun()
                        else:
                            note = st.text_input(
                                "Ghi chú nguyên nhân:",
                                placeholder="Ví dụ: Thối rễ do tưới nhiều",
                                key=f"del_note_{p['id']}"
                            )
                            st.caption("Lưu lại để AI học tránh lặp lại.")
                            if st.button("🗑️ Xóa & Lưu bài học",
                                         key=f"btn_del_learn_{p['id']}",
                                         type="primary"):
                                p.setdefault("logs", []).append({
                                    "d": datetime.now().strftime("%d/%m %H:%M"),
                                    "c": f"❌ {reason}. "
                                         + (f"Nguyên nhân: {note}" if note else "")
                                })
                                data = archive_and_delete_plant(data, p["id"])
                                st.rerun()

                    if weather.get("temp") is not None:
                        st.metric("🌡️", f"{weather['temp']}°C")
                        st.metric("💧", f"{weather['hum']}%")
                        if weather.get("wind") is not None:
                            st.metric("💨", f"{weather['wind']} km/h")
                    dp        = fetch_disease_pressure(lat, lon)
                    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
                    st.metric("🦠 7 ngày", f"{risk_icon} {dp.get('score',0)}/100")
# =============================================================
# 🩺 BÁC SĨ AI & CAMERA
# =============================================================

elif menu == "🩺 Bác sĩ AI & Camera":
    back_button()
    st.title("🩺 Bác sĩ AI Thực địa")

    st.info(
        "💡 **Quy trình:** Chụp ảnh → AI tự nhận diện & chẩn đoán "
        "kết hợp thời tiết + áp lực bệnh 7 ngày.\n\n"
        "**Mẹo:** Đủ ánh sáng | Cận cảnh vết bệnh | Để lá lành trong khung."
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
        st.sidebar.caption(f"🌤️ {w.get('desc','')}")
    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
    st.sidebar.metric("🦠 Áp lực bệnh",
                      f"{risk_icon} {dp.get('level','?').upper()}",
                      f"Score: {dp.get('score',0)}/100")

    # Danh sach cay de AI doi chieu -- KHONG can chon truoc
    all_plants = data.get("plants", [])
    if all_plants:
        plants_detail = []
        for pl in all_plants:
            try:
                si_ = get_current_stage(pl)
                age_days = si_["age"]
            except Exception:
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

    img_file = st.camera_input("📸 Chụp ảnh — AI tự nhận diện, không cần chọn cây trước")

    if img_file:
        image = Image.open(img_file)
        st.image(image, caption="Ảnh thực địa", width=500)

        if st.button("🚀 Phân tích & Chẩn đoán",
                     type="primary", key="btn_cam_ai"):

            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
            img_bytes = buf.getvalue()

            weather_ctx = (
                f"Nhiệt độ: {w['temp']}°C | Độ ẩm: {w['hum']}% | "
                f"Gió: {w.get('wind','?')} km/h | {w.get('desc','')}"
                if w["temp"] is not None else "Không có dữ liệu thời tiết."
            )
            agri_warns = weather.get("agri_warnings", [])
            dp_summary = (
                f"Áp lực bệnh 7 ngày: {dp.get('level','?').upper()} "
                f"(score {dp.get('score',0)}/100, "
                f"{dp.get('hours_risk',0)}h nguy hiểm, "
                f"cao điểm lúc {dp.get('peak_time','?')})"
            )

            full_prompt = f"""
Bạn là Bác sĩ cây trồng chuyên nghiệp. Dù cây gì cũng PHẢI chẩn đoán.
Trả lời BẰNG TIẾNG VIỆT, ngắn gọn, tối đa 300 từ.

VƯỜN HIỆN TẠI: {plants_detail_str}
THỜI TIẾT: {weather_ctx}
{dp_summary}
CẢNH BÁO: {', '.join(agri_warns) if agri_warns else 'Không có'}

### 🌿 1. NHẬN DIỆN CÂY
Tên cây + nếu có trong vườn thì ghi tên định danh.
Nếu không có trong vườn: "⚠️ Chưa có trong danh sách vườn"

### 🦠 2. CHẨN ĐOÁN
**Bệnh (nếu có):** Tên + tác nhân + mức độ
**Sâu hại (nếu có):** Tên + kiểu gây hại
**Dinh dưỡng (nếu có dấu hiệu):**
- Vàng lá già → thiếu Đạm (N)
- Vàng giữa gân xanh → thiếu Magie (Mg) / Sắt (Fe)
- Lá đỏ tím → thiếu Lân (P)
- Mép lá cháy nâu → thiếu Kali (K)
- Chồi non chết/biến dạng → thiếu Canxi (Ca) / Bo (B)
- Đốm vàng lá non → thiếu Mangan (Mn)
- Lá nhỏ, đốt ngắn → thiếu Kẽm (Zn)
- Vàng lá non đồng đều → thiếu Lưu huỳnh (S)
- Lá xanh đậm, ít trái → thừa Đạm (N)
- Mép lá cháy + khó hút dinh dưỡng → thừa Kali (K)
- Lá cháy rìa, đất trắng → thừa muối
**Nếu cây khỏe:** "✅ Cây khỏe" + lời khuyên phòng ngừa

### ⚡ 3. LÀM NGAY (24h) — tối đa 3 bước

### 💊 4. THUỐC & CÁCH DÙNG
| Loại | Sản phẩm | Liều lượng | Cách dùng |
|------|---------|------------|-----------|
| 🌿 Sinh học | ... | ... | ... |
| ⚗️ Hóa học | ... | ... | ... |
| 🧪 Dinh dưỡng | ... | ... | ... |

### 📈 5. KẾT LUẬN
Mức độ: [🟢/🟡/🔴/⛔] | Lây lan: [Thấp/Cao] | 1 câu quan trọng nhất.
"""

            with st.spinner("🔬 Bác sĩ AI đang phân tích..."):
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
                            "in_garden": matched_plant is not None,
                        }
                    else:
                        st.warning("⚠️ AI không phản hồi. Vui lòng thử lại.")
                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")
                    st.info("Kiểm tra kết nối mạng hoặc GEMINI_API_KEY.")

    # Ket qua -- NGOAI if img_file
    diag = st.session_state.get("last_diagnosis")
    if diag:
        st.markdown("---")
        st.subheader("🔬 Kết quả chẩn đoán")
        st.markdown(diag["result"])
        st.markdown("---")

        # 2 che do luu / khong luu
        col_mode1, col_mode2 = st.columns(2)
        with col_mode1:
            if st.button("💾 Lưu vào nhật ký vườn",
                         use_container_width=True, key="btn_mode_save"):
                st.session_state["show_save_options"] = True
        with col_mode2:
            if st.button("🚫 Không lưu, đóng lại",
                         use_container_width=True, key="btn_mode_nosave"):
                del st.session_state["last_diagnosis"]
                st.session_state.pop("show_save_options", None)
                st.rerun()

        if st.session_state.get("show_save_options"):
            st.markdown("#### 💾 Lưu vào đâu?")

            if diag.get("in_garden") and diag.get("plant"):
                plant_name = diag["plant"]["name"]
                st.success(f"🎯 AI nhận diện khớp: **{plant_name}**")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(f"✅ Lưu vào '{plant_name}'",
                                 use_container_width=True, key="btn_save_matched"):
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
                        st.session_state.pop("show_save_options", None)
                        st.success(f"✅ Đã lưu vào **{plant_name}**!")
                        st.rerun()
                with col_b:
                    if st.button("✅ Đã xử lý xong",
                                 type="primary", use_container_width=True,
                                 key="btn_done_matched"):
                        for p in data["plants"]:
                            if p["id"] == diag["plant"]["id"]:
                                p.setdefault("logs", []).append({
                                    "d": datetime.now().strftime("%d/%m %H:%M"),
                                    "c": "✅ Đã xử lý bệnh theo Bác sĩ AI."
                                })
                                break
                        save_data(data)
                        del st.session_state["last_diagnosis"]
                        st.session_state.pop("show_save_options", None)
                        st.rerun()

            # Chon cay thu cong
            if all_plants:
                st.markdown("**Hoặc chọn cây khác:**")
                manual_plant = st.selectbox(
                    "Chọn cây:",
                    all_plants,
                    format_func=lambda x: x["name"],
                    key="sb_manual_save"
                )
                if st.button("💾 Lưu vào cây này",
                             use_container_width=True, key="btn_save_manual"):
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
                    st.session_state.pop("show_save_options", None)
                    st.success(f"✅ Đã lưu vào **{manual_plant['name']}**!")
                    st.rerun()

            # Them cay moi tu camera
            with st.expander("➕ Thêm cây mới từ chẩn đoán này"):
                with st.form("form_add_from_camera"):
                    new_name  = st.text_input("Tên định danh vụ",
                                               placeholder="Ví dụ: Ớt sừng - Lứa 02")
                    new_date  = st.date_input("Ngày trồng xuống đất",
                                               value=datetime.now())
                    submitted = st.form_submit_button("🚀 Thêm vào vườn")
                    if submitted and new_name.strip():
                        data = add_plant(data, new_name,
                                         new_date.strftime("%Y-%m-%d"),
                                         extra={"date_seed_soak": None,
                                                "date_seedling":  None,
                                                "date_harvest":   None})
                        summary = diag["result"][:120].rsplit(" ", 1)[0] + "..."
                        data["plants"][-1].setdefault("logs", []).append({
                            "d": datetime.now().strftime("%d/%m %H:%M"),
                            "c": f"🩺 AI Chẩn đoán lần đầu: {summary}"
                        })
                        save_data(data)
                        del st.session_state["last_diagnosis"]
                        st.session_state.pop("show_save_options", None)
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
        f"📍 {city} | {temp_now}°C — {hum_now}% ẩm — Gió {wind_now} km/h"
        + (f" | VPD {vpd_now} kPa" if vpd_now else "")
        + f" | 🦠 {risk_icon} {dp.get('level','?').upper()}"
    )

    # 2 che do chat
    col_mode1, col_mode2 = st.columns(2)
    with col_mode1:
        if st.button(
            "🌱 Hỏi về vườn của mình",
            type="primary" if not st.session_state.get("chat_guest_mode") else "secondary",
            use_container_width=True, key="btn_mode_my_garden"
        ):
            st.session_state["chat_guest_mode"] = False
            st.rerun()
    with col_mode2:
        if st.button(
            "🌍 Hỏi chung (không lưu)",
            type="primary" if st.session_state.get("chat_guest_mode") else "secondary",
            use_container_width=True, key="btn_mode_guest"
        ):
            st.session_state["chat_guest_mode"] = True
            st.session_state.pop("guest_chat_history", None)
            st.rerun()

    guest_mode = st.session_state.get("chat_guest_mode", False)

    if guest_mode:
        st.info("🌍 **Hỏi chung** — Không lưu, dùng khi hỏi cho người khác.")
    else:
        st.info("🌱 **Vườn của mình** — AI đối chiếu nhật ký để tư vấn sát thực tế.")

    # Hien thi lich su chat
    if guest_mode:
        guest_history = st.session_state.get("guest_chat_history", [])
        for chat in guest_history:
            with st.chat_message("user"):
                st.write(chat["user"])
            with st.chat_message("assistant"):
                st.markdown(chat["ai"])

        # Gioi han 10 cau hoi khach
        if len(guest_history) >= 10:
            st.warning("⚠️ Đã đạt giới hạn 10 câu hỏi. Nhấn để bắt đầu lại.")
            if st.button("🔄 Bắt đầu hội thoại mới", key="btn_reset_guest"):
                st.session_state["guest_chat_history"] = []
                st.rerun()
        if guest_history:
            if st.button("🗑️ Xóa hội thoại", key="btn_clear_guest"):
                st.session_state["guest_chat_history"] = []
                st.rerun()
    else:
        # Gioi han 20 tin nhan
        chat_history = data.get("chat_history", [])[-20:]
        for chat in chat_history:
            with st.chat_message("user"):
                st.write(chat["user"])
            with st.chat_message("assistant"):
                st.markdown(chat["ai"])

        if data.get("chat_history"):
            col_del1, col_del2 = st.columns(2)
            with col_del1:
                if st.button("🗑️ Xóa tin cuối", key="btn_del_last"):
                    data["chat_history"] = data["chat_history"][:-1]
                    save_data(data)
                    st.rerun()
            with col_del2:
                if st.button("🗑️ Xóa tất cả", key="btn_clear_all"):
                    data["chat_history"] = []
                    save_data(data)
                    st.rerun()

    # Kiem tra gioi han truoc khi cho nhap
    guest_history = st.session_state.get("guest_chat_history", [])
    can_chat = not guest_mode or len(guest_history) < 10

    if can_chat:
        if prompt := st.chat_input("Hỏi AI về kỹ thuật vườn, phân bón, sâu bệnh..."):
            with st.chat_message("user"):
                st.write(prompt)

            with st.spinner("🤖 AI đang phân tích..."):
                try:
                    # Tong hop nhat ky cay (chi trong che do vuon minh)
                    if not guest_mode:
                        plant_history = []
                        for pl in data.get("plants", []):
                            si_      = get_current_stage(pl)
                            parts_   = pl["name"].split("|", 1)
                            cname_   = parts_[1].strip() if len(parts_) > 1 else parts_[0].strip()
                            logs_    = " → ".join([f"{l['d']}: {l['c']}"
                                                   for l in pl.get("logs", [])[-3:]])
                            plant_history.append(
                                f"• {cname_} ({si_['age']} ngày — {si_['label']})"
                                + (f"\n  Nhật ký: {logs_}" if logs_ else "")
                                + (f"\n  Thu hoạch: {pl['date_harvest']}"
                                   if pl.get("date_harvest") else "")
                            )
                        garden_ctx = (
                            "=== CÂY TRONG VƯỜN ===\n" + "\n".join(plant_history)
                            if plant_history else ""
                        )
                    else:
                        garden_ctx = ""

                    w_ctx = (
                        f"Nhiệt độ {temp_now}°C, Độ ẩm {hum_now}%, Gió {wind_now} km/h"
                        + (f", VPD {vpd_now} kPa ({vpd_label})" if vpd_now else "")
                        + f". Áp lực bệnh: {dp.get('level','?').upper()} "
                        f"(score {dp.get('score',0)}/100)"
                    )

                    full_prompt = f"""
Bạn là Chuyên gia Nông nghiệp, đang tư vấn cho {"chủ vườn" if not guest_mode else "nông dân"}.
Trả lời BẰNG TIẾNG VIỆT, tối đa 200 từ, ngắn gọn, dễ hiểu.

=== THỜI TIẾT tại {city} ===
{w_ctx}
{garden_ctx}
=== CÂU HỎI ===
{prompt}

Yêu cầu:
{"- Đối chiếu nhật ký cây để tư vấn SÁT THỰC TẾ." if not guest_mode else "- Trả lời tổng quát."}
- Ưu tiên giải pháp hữu cơ/sinh học.
- Có tính đến VPD và áp lực bệnh khi tư vấn.
- Dùng Markdown để trình bày rõ ràng.
"""
                    response = model.generate_content(
                        full_prompt,
                        request_options={"timeout": 60}
                    )
                    ai_res = (
                        response.text if hasattr(response, "text")
                        else "⚠️ AI không thể trả lời."
                    )

                    with st.chat_message("assistant"):
                        st.markdown(ai_res)

                    if guest_mode:
                        guest_history.append({"user": prompt, "ai": ai_res})
                        st.session_state["guest_chat_history"] = guest_history
                    else:
                        add_chat(data, prompt, ai_res)
                        if len(data.get("chat_history", [])) > 20:
                            data["chat_history"] = data["chat_history"][-20:]
                        save_data(data)
                    st.rerun()

                except Exception as e:
                    st.error(f"⚠️ Lỗi kết nối AI: {e}")
                    st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets.")                    
                    
