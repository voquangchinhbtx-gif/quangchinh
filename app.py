"""
app.py - GREEN FARM
Bo sung:
  - Du bao 7 ngay (tam nhin xa)
  - Ap luc benh 48h (canh bao nam)
  - So khop 3 ben AI (nhat ky + thoi tiet + quy trinh)
  - Nut "Da thuc hien" (tuong tac nhat ky)

Chay: streamlit run app.py
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
from weather import (
    get_weather, get_city_name,
    get_forecast_7day, get_disease_pressure_48h
)

# =============================================================
# CAU HINH GEMINI
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
    return genai.GenerativeModel(model_name)


model = get_gemini_model(GEMINI_MODEL)

# =============================================================
# CONSTANTS
# =============================================================

DEFAULT_LAT, DEFAULT_LON = 10.7769, 106.7009

CROP_LIST = [
    "Ot Aji Charapita", "Ot Chi thien", "Ot Xiem",
    "Bau", "Mai vang", "Ca chua Beef", "Dua leo",
    "Chanh", "Ca tim", "Bap cai", "Xa lach",
    "Rau muong", "Hung que", "Can tay", "Khac"
]

WMO_MAP = {
    0: "Troi quang",    1: "It may",           2: "May rai rac",
    3: "Nhieu may",    45: "Suong mu",         48: "Suong mu co bang",
    51: "Mua phun nhe", 53: "Mua phun",        55: "Mua phun day",
    61: "Mua nho",      63: "Mua vua",          65: "Mua to",
    80: "Mua rao nhe",  81: "Mua rao",          82: "Mua rao nang",
    95: "Dong bao",    96: "Dong co mua da",   99: "Dong mua da lon",
}

RISK_COLOR = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔", "unknown": "⚪"}

# =============================================================
# HELPERS
# =============================================================

def calculate_vpd(temp: float, humidity: float) -> float:
    svp = 0.61078 * math.exp((17.27 * temp) / (temp + 237.3))
    return round(svp * (1 - humidity / 100), 3)


def safe_weather_str(w: dict) -> str:
    if not w or w.get("temp") is None:
        return "N/A"
    return f"{w.get('temp','?')}°C, {w.get('hum','?')}% am"


def build_season_context(history: list) -> str:
    if not history:
        return "Chua co du lieu vu truoc."
    lines = []
    for i, s in enumerate(history[-3:], 1):
        lines.append(f"--- Vu {i} ({s.get('date_start','')} -> {s.get('date_end','')}) ---")
        logs = s.get("logs", [])
        if logs:
            log_texts = [
                f"{l.get('d', l.get('date',''))}: {l.get('c', l.get('content',''))}"
                for l in logs[-10:]
            ]
            lines.append("Nhat ky: " + " | ".join(log_texts))
        recipe = s.get("recipe", "")
        if recipe:
            lines.append(f"Quy trinh AI vu do: {recipe[:300]}...")
    return "\n".join(lines)


def get_weather_safe() -> dict:
    return {
        "temp": None, "hum": None, "wind": None,
        "rain": None, "desc": "Dang tai...",
        "city": "Dang xac dinh vi tri...",
        "lat": DEFAULT_LAT, "lon": DEFAULT_LON,
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
# XAC THUC
# =============================================================

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🌿 GREEN FARM")
        st.markdown("### 🔐 Dang nhap")
        password = st.text_input("Nhap mat khau:", type="password", key="login_pw")
        if st.button("Dang nhap"):
            try:
                correct_pw = st.secrets["APP_PASSWORD"]
            except (KeyError, FileNotFoundError):
                correct_pw = "greenfarm2024"
            if password == correct_pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Mat khau khong dung!")
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
    with st.spinner("📍 Dang xac dinh vi tri GPS thuc te..."):
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
            "desc": WMO_MAP.get(code, "Khong xac dinh"),
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
# TAI DU LIEU
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
    gps_source = "📡 GPS thuc" if st.session_state["gps_resolved"] else "📌 Mac dinh"
    st.caption(f"{gps_source}: {lat:.4f}, {lon:.4f}")

    menu_options = [
        "📊 Dashboard",
        "🌱 Quan ly Cay trong",
        "🩺 Bac si AI & Camera",
        "💬 Tro ly Ky thuat",
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
        if st.button("⬅️ Quay lai"):
            st.session_state["menu_choice"] = st.session_state["prev_menu"]
            st.rerun()

# =============================================================
# COMPONENT: DU BAO 7 NGAY
# =============================================================

def render_forecast_7day(lat: float, lon: float):
    st.markdown("### 🗓️ Du bao 7 ngay (Tam nhin xa)")
    forecast = fetch_forecast_7day(lat, lon)
    if not forecast:
        st.warning("Khong lay duoc du bao 7 ngay.")
        return

    cols = st.columns(7)
    for i, day in enumerate(forecast):
        with cols[i]:
            risk_icon = RISK_COLOR.get(day["risk"], "⚪")
            label     = "Hom nay" if i == 0 else fmt_date(day["date"])
            st.markdown(f"**{label}**")
            st.markdown(f"{risk_icon}")
            st.caption(f"↑{day['temp_max']:.0f}° ↓{day['temp_min']:.0f}°")
            st.caption(f"💧{day['hum_max']:.0f}%")
            if day["rain"] > 0:
                st.caption(f"🌧️{day['rain']:.1f}mm")
            st.caption(day["desc"][:12])

    st.caption("🟢 An toan  🟡 Can theo doi  🔴 Nguy co cao  ⛔ Cuc ky nguy hiem")

# =============================================================
# COMPONENT: AP LUC BENH 48H
# =============================================================

def render_disease_pressure_48h(lat: float, lon: float):
    st.markdown("### 🦠 Ap luc benh 48h")
    dp = fetch_disease_pressure(lat, lon)

    level      = dp.get("level", "unknown")
    score      = dp.get("score", 0)
    hours_risk = dp.get("hours_risk", 0)
    peak_time  = dp.get("peak_time", "")
    warnings   = dp.get("warnings", [])

    col1, col2, col3 = st.columns(3)
    icon = RISK_COLOR.get(level, "⚪")
    col1.metric("Muc do rui ro", f"{icon} {level.upper()}", f"Score: {score}/100")
    col2.metric("Gio nguy hiem", f"{hours_risk}h / 48h")
    col3.metric("Cao diem", peak_time if peak_time else "N/A")

    st.progress(min(score, 100))

    for w in warnings:
        if level in ("critical", "high"):
            st.error(w)
        elif level == "medium":
            st.warning(w)
        else:
            st.success(w)

# =============================================================
# COMPONENT: SO KHOP 3 BEN AI
# =============================================================

def render_three_way_match(p: dict, crop_type: str, age: int):
    st.markdown("### 🧠 Bo nao nhac nho (So khop 3 ben)")

    if st.button("🔄 Phan tich & Nhac viec", key=f"btn_3way_{p['id']}"):
        current_logs  = " | ".join([l["c"] for l in p.get("logs", [])[-5:]])
        std_recipe    = p.get("standard_recipe", "Chua co quy trinh chuan.")[:500]
        warnings_list = weather.get("agri_warnings", [])
        dp            = fetch_disease_pressure(lat, lon)

        prompt = f"""
Ban la AI quan ly vuon thong minh. Tra loi BANG TIENG VIET.

=== NGUON 1: NHAT KY THUC TE ===
Cay: {crop_type} | Tuoi: {age} ngay
Nhat ky 5 dong gan nhat: {current_logs if current_logs else "Chua co"}

=== NGUON 2: THOI TIET + AP LUC BENH ===
Hien tai: {safe_weather_str(weather)}
Canh bao: {', '.join(warnings_list) if warnings_list else 'Khong co'}
Ap luc benh 48h: {dp.get('level','?').upper()} (score {dp.get('score',0)}/100, {dp.get('hours_risk',0)}h nguy hiem)

=== NGUON 3: QUY TRINH CHUAN ===
{std_recipe}

=== NHIEM VU ===
So sanh 3 nguon tren, tim ra NHUNG VIEC BI BO SOT hoac CAN LAM NGAY.
Tra loi NGAN GON, TOI DA 5 viec, moi viec 1 dong, bat dau bang emoji hanh dong.
Format bat buoc:
VIEC_1: [mo ta ngan gon, tai sao can lam ngay]
VIEC_2: ...
(chi liet ke viec thuc su can thiet, khong them giai thich dai dong)
"""
        with st.spinner("AI dang so sanh 3 nguon du lieu..."):
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

                if tasks:
                    st.session_state[f"tasks_3way_{p['id']}"] = tasks
                    st.rerun()
                else:
                    st.session_state[f"tasks_3way_{p['id']}"] = [
                        line.strip() for line in text.strip().split("\n")
                        if line.strip() and len(line.strip()) > 10
                    ][:5]
                    st.rerun()
            except Exception as e:
                st.error(f"Loi AI so khop: {e}")

    tasks = st.session_state.get(f"tasks_3way_{p['id']}", [])
    if tasks:
        st.markdown("**📋 Viec can lam (tu so khop 3 ben):**")
        for idx, task in enumerate(tasks):
            col_task, col_btn = st.columns([4, 1])
            with col_task:
                st.markdown(f"• {task}")
            with col_btn:
                if st.button("✅ Xong", key=f"done_3way_{p['id']}_{idx}"):
                    p.setdefault("logs", []).append({
                        "d": datetime.now().strftime("%d/%m %H:%M"),
                        "c": f"✅ Da thuc hien (AI nhac): {task[:80]}"
                    })
                    remaining = [t for j, t in enumerate(tasks) if j != idx]
                    if remaining:
                        st.session_state[f"tasks_3way_{p['id']}"] = remaining
                    else:
                        del st.session_state[f"tasks_3way_{p['id']}"]
                    save_data(data)
                    st.success("Da ghi vao nhat ky!")
                    st.rerun()

# =============================================================
# 📊 DASHBOARD
# =============================================================

if menu == "📊 Dashboard":
    back_button()
    st.title("📊 Quan trac VPD & Thoi tiet")
    st.markdown(f"📍 **{weather.get('city', '...')}**")

    if weather.get("temp") is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌡️ Nhiet do",  f"{weather['temp']}°C")
        c2.metric("💧 Do am",     f"{weather['hum']}%")
        c3.metric("🌧️ Mua",       f"{weather['rain']} mm")
        c4.metric("🌤️ Thoi tiet", weather["desc"])

        if weather.get("wind") is not None:
            wind_val   = weather["wind"]
            wind_delta = (
                "⛔ Rat manh" if wind_val >= 40
                else "⚠️ Vua"  if wind_val >= 20
                else "✅ Nhe"
            )
            st.metric("💨 Gio", f"{wind_val} km/h", wind_delta)

        vpd = calculate_vpd(weather["temp"], weather["hum"])
        st.markdown(f"### Chi so VPD: `{vpd:.2f} kPa`")
        if vpd < 0.5:
            st.error("🦠 Nguy co nam benh cao (VPD qua thap)")
        elif vpd > 2.0:
            st.warning("🌵 Khong khi qua kho (VPD cao)")
        else:
            st.success("✅ Dieu kien sinh truong tot")

        warnings = weather.get("agri_warnings", [])
        if warnings:
            st.markdown("### 🚨 Canh bao Nong nghiep")
            for w in warnings:
                st.info(w)

        st.divider()
        render_forecast_7day(lat, lon)
        st.divider()
        render_disease_pressure_48h(lat, lon)

    else:
        st.info("⏳ Dang tai du lieu thoi tiet...")

# =============================================================
# 🌱 QUAN LY CAY TRONG
# =============================================================

elif menu == "🌱 Quan ly Cay trong":
    back_button()
    st.title("🌱 Quan ly Vuon & He thong Toi uu AI")

    with st.expander("⚙️ Thiet lap & Quan ly danh sach cay", expanded=False):
        tab_add, tab_edit = st.tabs(["➕ Them cay moi", "✏️ Chinh sua thong tin"])

        with tab_add:
            crop_select = st.selectbox("🌿 Chon loai cay trong", CROP_LIST,
                                       key="crop_select")
            type_in = (
                st.text_input("Nhap ten loai cay",
                              placeholder="Vi du: Ot Aji Charapita",
                              key="add_type_custom")
                if crop_select == "Khac" else crop_select
            )
            name_in = st.text_input("Ten dinh danh vu",
                                    placeholder="Vi du: Ot Aji - Lua 01",
                                    key="add_name")
            st.markdown("##### 📅 Cac moc thoi gian")
            c1, c2 = st.columns(2)
            with c1:
                date_seed_soak  = st.date_input("🫧 Ngay u hat",
                                                value=datetime.now(),
                                                key="date_seed_soak")
                date_transplant = st.date_input("🌱 Ngay trong xuong dat",
                                                value=datetime.now(),
                                                key="date_transplant")
            with c2:
                date_seedling = st.date_input("🌿 Ngay gieo uom",
                                              value=datetime.now(),
                                              key="date_seedling")
                st.caption("🍅 Ngay thu hoach do AI tu tinh sau khi tao quy trinh.")

            if st.button("🚀 Khoi tao vuon", key="btn_init_farm"):
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
                    st.success(f"Da them **{name_in}**! Nhan 🌱 Tao quy trinh chuan de AI tinh ngay thu hoach.")
                    st.rerun()
                else:
                    st.warning("Vui long dien du Ten va Loai cay.")

        with tab_edit:
            all_p = data.get("plants", [])
            if all_p:
                p_edit = st.selectbox("Chon cay muon sua", all_p,
                                      format_func=lambda x: x["name"],
                                      key="sb_edit")
                new_n = st.text_input("Sua ten dinh danh",
                                      value=p_edit["name"], key="edit_name")
                st.markdown("##### 📅 Cac moc thoi gian")
                c1, c2 = st.columns(2)
                with c1:
                    try:
                        val_ss = (datetime.strptime(p_edit["date_seed_soak"], "%Y-%m-%d")
                                  if p_edit.get("date_seed_soak") else datetime.now())
                    except (ValueError, TypeError):
                        val_ss = datetime.now()
                    new_ss = st.date_input("🫧 Ngay u hat",
                                           value=val_ss, key="edit_seed_soak")
                    try:
                        val_tr = datetime.strptime(p_edit["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        val_tr = datetime.now()
                    new_d = st.date_input("🌱 Ngay trong xuong dat",
                                          value=val_tr, key="edit_date")
                with c2:
                    try:
                        val_sl = (datetime.strptime(p_edit["date_seedling"], "%Y-%m-%d")
                                  if p_edit.get("date_seedling") else datetime.now())
                    except (ValueError, TypeError):
                        val_sl = datetime.now()
                    new_sl = st.date_input("🌿 Ngay gieo uom",
                                           value=val_sl, key="edit_seedling")
                    st.text_input("🍅 Du kien thu hoach (do AI tinh)",
                                  value=p_edit.get("date_harvest") or "Chua co",
                                  disabled=True, key="edit_harvest_display")

                if st.button("💾 Luu cap nhat", key="btn_update"):
                    for p in data["plants"]:
                        if p["id"] == p_edit["id"]:
                            p["name"]           = new_n
                            p["date"]           = new_d.strftime("%Y-%m-%d")
                            p["date_seed_soak"] = new_ss.strftime("%Y-%m-%d")
                            p["date_seedling"]  = new_sl.strftime("%Y-%m-%d")
                    save_data(data)
                    st.success("Da cap nhat!")
                    st.rerun()
            else:
                st.info("Chua co cay nao de sua.")

    plants_list = data.get("plants", [])
    if not plants_list:
        st.info("🌵 Vuon hien tai chua co cay. Hay them cay moi o tren.")
    else:
        with st.expander("🦠 Ap luc benh 48h toan vuon", expanded=False):
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
                    st.write(f"⏱️ **{age} ngay tuoi**")
                    if p.get("date_seed_soak"):
                        st.caption(f"🫧 U hat: {p['date_seed_soak']}")
                    if p.get("date_seedling"):
                        st.caption(f"🌿 Gieo uom: {p['date_seedling']}")
                    st.caption(
                        f"🍅 Thu hoach: {p['date_harvest']}"
                        if p.get("date_harvest") else "🍅 Thu hoach: Chua co"
                    )
                    st.divider()
                    with st.popover("📖 Nhat ky vuon"):
                        st.write(f"📝 Ghi chep cho **{p['name']}**")
                        log_text = st.text_area("Hom nay co gi moi?",
                                                key=f"log_area_{p['id']}")
                        if st.button("Luu nhat ky", key=f"btn_log_{p['id']}"):
                            if log_text.strip():
                                p.setdefault("logs", []).append({
                                    "d": datetime.now().strftime("%d/%m %H:%M"),
                                    "c": log_text.strip()
                                })
                                save_data(data)
                                st.success("Da ghi so!")
                                st.rerun()
                            else:
                                st.warning("Nhat ky khong duoc de trong.")
                        st.write("---")
                        recent_logs = list(reversed(p.get("logs", [])))[:5]
                        if recent_logs:
                            for log in recent_logs:
                                st.caption(f"📅 {log['d']}: {log['c']}")
                        else:
                            st.caption("Chua co nhat ky nao.")

                with col_care:
                    parts     = p["name"].split("|", 1)
                    crop_type = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    st.markdown(f"📋 **Phac do toi uu AI cho: {crop_type}**")

                    # Nut 1: Tao quy trinh chuan
                    if st.button("🌱 Tao quy trinh chuan", key=f"btn_std_{p['id']}"):
                        with st.spinner("AI dang tao quy trinh chuan..."):
                            try:
                                res = model.generate_content(
                                    f"""Ban la chuyen gia nong nghiep huu co. Tra loi BANG TIENG VIET.
Loai cay: {crop_type}
Ngay u hat: {p.get('date_seed_soak', 'Chua co')}
Ngay gieo uom: {p.get('date_seedling', 'Chua co')}
Ngay trong xuong dat: {p.get('date', 'Chua co')}
Thoi tiet hien tai: {safe_weather_str(weather)}

Hay tao QUY TRINH CHUAN TOAN VU tu u hat den thu hoach:

### 🫧 GIAI DOAN U HAT & GIEO UOM
### 🌱 GIAI DOAN CAY CON (0-30 ngay)
### 🌿 GIAI DOAN PHAT TRIEN (30-60 ngay)
### 🌸 GIAI DOAN RA HOA / KET TRAI
### 🍅 GIAI DOAN THU HOACH
### ⚠️ CAC BENH THUONG GAP & CACH XU LY
| Benh/Sau | Dau hieu | Xu ly sinh hoc | Xu ly hoa hoc |
|----------|----------|----------------|---------------|

### 📆 DU KIEN NGAY THU HOACH
Ngay thu hoach du kien: YYYY-MM-DD""",
                                    request_options={"timeout": 30}
                                )
                                std_text = getattr(res, "text", None)
                                if std_text:
                                    p["standard_recipe"] = std_text
                                    match = re.search(
                                        r"Ngay thu hoach du kien:\s*(\d{4}-\d{2}-\d{2})",
                                        std_text
                                    )
                                    if match:
                                        p["date_harvest"] = match.group(1)
                                    save_data(data)
                                    st.session_state[f"std_view_{p['id']}"] = std_text
                                    st.rerun()
                                else:
                                    st.warning("AI khong tra ve ket qua.")
                            except Exception as e:
                                st.error(f"Loi AI: {e}")

                    std_display = st.session_state.get(
                        f"std_view_{p['id']}", p.get("standard_recipe"))
                    if std_display:
                        with st.expander("📋 XEM QUY TRINH CHUAN", expanded=False):
                            st.markdown(std_display)

                    st.divider()

                    # Nut 2: Phan tich hom nay
                    if st.button("🔍 Phan tich tinh trang hom nay",
                                 key=f"btn_analyze_{p['id']}"):
                        with st.spinner("AI dang phan tich..."):
                            try:
                                current_logs  = " | ".join([l["c"] for l in p.get("logs", [])])
                                warnings_list = weather.get("agri_warnings", [])
                                dp            = fetch_disease_pressure(lat, lon)
                                res = model.generate_content(
                                    f"""Ban la chuyen gia nong nghiep huu co thuc chien. Tra loi BANG TIENG VIET.

=== THONG TIN CAY ===
- Loai cay: {crop_type} | Tuoi: {age} ngay
- Du kien thu hoach: {p.get('date_harvest', 'Chua co')}

=== THOI TIET & AP LUC BENH ===
{safe_weather_str(weather)}
Canh bao: {', '.join(warnings_list) if warnings_list else 'Khong co'}
Ap luc benh 48h: {dp.get('level','?').upper()} - {dp.get('hours_risk',0)}h nguy hiem

=== NHAT KY GAN NHAT ===
{current_logs if current_logs else "Chua co nhat ky"}

### 🌡️ DANH GIA TINH TRANG HIEN TAI
### 💊 PHAN BON CAN BO SUNG NGAY
| Loai phan | Lieu luong | Cach bon | Thoi diem |
|-----------|-----------|----------|-----------|
### 🛡️ PHONG TRI SAU BENH (co tinh den ap luc benh 48h)
| Doi tuong | Dau hieu | Xu ly sinh hoc | Xu ly hoa hoc |
|-----------|----------|----------------|---------------|
### 📅 LICH 7 NGAY TOI
| Ngay | Viec can lam | Luu y |
|------|-------------|-------|
### ⚡ HANH DONG NGAY HOM NAY
Liet ke dung 3 viec quan trong nhat, moi viec 1 dong.""",
                                    request_options={"timeout": 30}
                                )
                                analyze_text = getattr(res, "text", None)
                                if analyze_text:
                                    p["daily_analysis"] = analyze_text
                                    save_data(data)
                                    st.session_state[f"analyze_view_{p['id']}"] = analyze_text
                                    actions = []
                                    in_action = False
                                    for line in analyze_text.split("\n"):
                                        if "HANH DONG NGAY HOM NAY" in line:
                                            in_action = True
                                            continue
                                        if in_action and line.strip().startswith(("1.", "2.", "3.", "-", "•")):
                                            clean = re.sub(r"^[\d\.\-•\*\s]+", "", line).strip()
                                            if clean:
                                                actions.append(clean)
                                        if in_action and line.startswith("#") and "HANH DONG" not in line:
                                            break
                                    if actions:
                                        st.session_state[f"actions_{p['id']}"] = actions[:3]
                                else:
                                    st.warning("AI khong tra ve ket qua.")
                            except Exception as e:
                                st.error(f"Loi AI: {e}")

                    analyze_display = st.session_state.get(
                        f"analyze_view_{p['id']}", p.get("daily_analysis"))
                    if analyze_display:
                        with st.expander("🔍 KET QUA PHAN TICH HOM NAY", expanded=True):
                            st.markdown(analyze_display)

                        actions = st.session_state.get(f"actions_{p['id']}", [])
                        if actions:
                            st.markdown("**⚡ Xac nhan hanh dong hom nay:**")
                            for idx, action in enumerate(actions):
                                col_act, col_done = st.columns([5, 1])
                                with col_act:
                                    st.markdown(f"`{idx+1}.` {action}")
                                with col_done:
                                    if st.button("✅ Xong",
                                                 key=f"done_action_{p['id']}_{idx}"):
                                        p.setdefault("logs", []).append({
                                            "d": datetime.now().strftime("%d/%m %H:%M"),
                                            "c": f"✅ Da thuc hien: {action[:80]}"
                                        })
                                        remaining = [a for j, a in enumerate(actions) if j != idx]
                                        if remaining:
                                            st.session_state[f"actions_{p['id']}"] = remaining
                                        else:
                                            del st.session_state[f"actions_{p['id']}"]
                                        save_data(data)
                                        st.success("Da ghi vao nhat ky!")
                                        st.rerun()

                    st.divider()

                    # Nut 3: Toi uu 15 ngay
                    if st.button("🧠 AI: Toi uu 15 ngay toi",
                                 key=f"btn_opt_{p['id']}"):
                        with st.spinner("Dang tong hop lich su..."):
                            try:
                                current_logs = " | ".join([l["c"] for l in p.get("logs", [])])
                                past_seasons = get_crop_history(data, crop_type)
                                season_ctx   = build_season_context(past_seasons)
                                forecast     = fetch_forecast_7day(lat, lon)
                                forecast_str = " | ".join([
                                    f"{fmt_date(d['date'])}: {d['desc']}, {d['temp_max']:.0f}°C, "
                                    f"am {d['hum_max']:.0f}%, {RISK_COLOR.get(d['risk'],'')} rui ro"
                                    for d in forecast
                                ])
                                res = model.generate_content(
                                    f"""Ban la chuyen gia nong nghiep huu co cap cao. Tra loi BANG TIENG VIET.

=== CAY HIEN TAI ===
- Loai: {crop_type} | Tuoi: {age} ngay | Thu hoach: {p.get('date_harvest', 'Chua co')}
- Thoi tiet hien tai: {safe_weather_str(weather)}
- Nhat ky: {current_logs if current_logs else "Chua co"}

=== DU BAO 7 NGAY TOI ===
{forecast_str}

=== {len(past_seasons)} VU TRUOC ===
{season_ctx}

### 📊 PHAN TICH GIAI DOAN SINH TRUONG
### 📊 HOC TU VU TRUOC
### 🌿 DINH DUONG (co tinh den du bao thoi tiet)
### 🛡️ BAO VE THUC VAT (uu tien phong ngua dua vao du bao)
### 🔧 DIEU CHINH TU NHAT KY
### 📅 LICH 15 NGAY
| Ngay  | Giai doan | Viec can lam | Luu y thoi tiet |
|-------|-----------|-------------|-----------------|
| 1-5   | ...       | ...         | ...             |
| 6-10  | ...       | ...         | ...             |
| 11-15 | ...       | ...         | ...             |""",
                                    request_options={"timeout": 30}
                                )
                                recipe_text = getattr(res, "text", None)
                                if recipe_text:
                                    p["optimized_recipe"] = recipe_text
                                    save_data(data)
                                    st.session_state[f"st_view_{p['id']}"] = recipe_text
                                else:
                                    st.warning("AI khong tra ve ket qua.")
                            except Exception as e:
                                st.error(f"Loi AI: {e}")

                    plan_display = st.session_state.get(
                        f"st_view_{p['id']}", p.get("optimized_recipe"))
                    if plan_display:
                        with st.expander("📍 XEM QUY TRINH TOI UU", expanded=False):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chua co quy trinh toi uu. Hay nhan nut AI.")

                    st.divider()

                    # So khop 3 ben
                    render_three_way_match(p, crop_type, age)

                with col_action:
                    st.caption("⚙️ Thao tac")
                    with st.popover("🗑️ Ket thuc vu"):
                        st.warning(f"Ket thuc vu **{p['name']}**?")
                        st.caption("Nhat ky & quy trinh se duoc luu de AI hoc vu sau.")
                        if st.button("✔️ Xac nhan",
                                     key=f"btn_del_{p['id']}", type="primary"):
                            data = archive_and_delete_plant(data, p["id"])
                            st.rerun()
                    if weather.get("temp") is not None:
                        st.metric("🌡️", f"{weather['temp']}°C")
                        st.metric("💧", f"{weather['hum']}%")
                        if weather.get("wind") is not None:
                            st.metric("💨", f"{weather['wind']} km/h")
                    dp = fetch_disease_pressure(lat, lon)
                    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
                    st.metric("🦠 Benh 48h", f"{risk_icon} {dp.get('score',0)}/100")

# =============================================================
# 🩺 BAC SI AI & CAMERA
# =============================================================

elif menu == "🩺 Bac si AI & Camera":
    back_button()
    st.title("🩺 Bac si AI Thuc dia")

    st.info(
        "💡 **Quy trinh:** Chup anh → AI phan tich anh + Meteo + Ap luc benh 48h "
        "→ Chan doan & Ke don dieu tri ngay lap tuc.\n\n"
        "**Meo chup anh:** Du anh sang | Can canh vet benh | De phan la lanh trong khung."
    )

    gps_lat = st.session_state["gps_lat"]
    gps_lon = st.session_state["gps_lon"]
    w       = fetch_meteo_direct(gps_lat, gps_lon)
    dp      = fetch_disease_pressure(gps_lat, gps_lon)

    if w["temp"] is not None:
        st.sidebar.metric("🌡️ Nhiet do", f"{w['temp']}°C")
        st.sidebar.metric("💧 Do am",    f"{w['hum']}%")
        if w["wind"] is not None:
            st.sidebar.metric("💨 Gio",  f"{w['wind']} km/h")
        st.sidebar.caption(f"🌤️ {w.get('desc', '')}")
    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")
    st.sidebar.metric("🦠 Ap luc benh 48h",
                      f"{risk_icon} {dp.get('level','?').upper()}",
                      f"Score: {dp.get('score',0)}/100")

    all_plants    = data.get("plants", [])
    plant_names   = [p["name"] for p in all_plants]
    plant_context = ", ".join(plant_names) if plant_names else "He thong tu nhan dien"

    selected_plant = None
    if all_plants:
        selected_plant = st.selectbox(
            "📌 Gan ket qua chan doan vao cay (tuy chon):",
            [None] + all_plants,
            format_func=lambda x: "— Khong gan —" if x is None else x["name"],
            key="sb_cam_plant"
        )

    img_file = st.camera_input("📸 Chup anh cay can chan doan")

    if img_file:
        image = Image.open(img_file)
        st.image(image, caption="Anh thuc dia", width=500)

        if st.button("🚀 Phan tich & Ke don dieu tri",
                     type="primary", key="btn_cam_ai"):

            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
            img_bytes = buf.getvalue()

            age_ctx = ""
            if selected_plant:
                try:
                    pd_ = datetime.strptime(selected_plant["date"], "%Y-%m-%d")
                    age_ctx = (
                        f"Cay dang o ngay thu "
                        f"{max((datetime.now() - pd_).days, 0)} ke tu khi trong."
                    )
                except (ValueError, KeyError):
                    pass

            if w["temp"] is not None:
                weather_ctx = (
                    f"Nhiet do: {w['temp']}°C | Do am: {w['hum']}% | "
                    f"Gio: {w.get('wind','?')} km/h | {w.get('desc','')}"
                )
            else:
                weather_ctx = "Khong co du lieu thoi tiet."

            agri_warns = weather.get("agri_warnings", [])
            dp_summary = (
                f"Ap luc benh 48h: {dp.get('level','?').upper()} "
                f"(score {dp.get('score',0)}/100, {dp.get('hours_risk',0)}h nguy hiem, "
                f"cao diem luc {dp.get('peak_time','?')})"
            )

            full_prompt = f"""
Ban la Bac si cay trong chuyen nghiep voi 20 nam kinh nghiem thuc dia tai Dong Nam A.

DANH MUC CAY TRONG VUON: {plant_context}
THOI TIET THUC DIA (GPS: {gps_lat:.4f}, {gps_lon:.4f}): {weather_ctx}
{dp_summary}
CANH BAO NONG NGHIEP: {', '.join(agri_warns) if agri_warns else 'Khong co'}
{age_ctx}

Nhiem vu -- phan tich anh va tra loi BANG TIENG VIET theo dung cau truc:

### 🌿 1. XAC DINH CAY
Day la cay gi? Neu trung ten trong danh muc vuon, goi dung ten dinh danh do.

### 🦠 2. CHAN DOAN
- Ten benh / sau hai va tac nhan (Nam / Vi khuan / Virus / Con trung / Thieu dinh duong).
- Dau hieu nhan biet cu the tu anh (mau sac, hinh dang, vi tri vet benh).
- Giai doan benh: [So nhiem / Dang phat trien / Nang]

### 🌧️ 3. LIEN HE THOI TIET & AP LUC BENH
Voi {weather_ctx} va {dp_summary},
benh co xu huong lan rong nhu the nao trong 48h toi? Canh bao cu the.

### 💊 4. PHAC DO DIEU TRI
- **Buoc 1 -- Xu ly ngay (24h):** Cat tia / cach ly / ve sinh vuon.
- **Buoc 2 -- Sinh hoc (Uu tien):** Ten san pham, hoat chat, lieu luong, cach dung.
- **Buoc 3 -- Hoa hoc (Khi can):** Hoat chat, lieu luong, luu y PHI.

### 📅 5. PHONG NGUA 7 NGAY TOI
Lich cham soc cu the theo tung ngay de khong tai phat.

### 📈 6. TIEN LUONG
- Muc do nguy hiem: [🟢 Thap / 🟡 Trung binh / 🔴 Cao / ⛔ Khan cap]
- Nguy co lay lan: [Thap / Cao -- ly do]
- Hanh dong QUAN TRONG NHAT trong 24h.

Ngon ngu: binh dan, de hieu cho nong dan Viet Nam.
"""

            with st.spinner("🔬 Bac si AI dang phan tich anh va du lieu thuc dia..."):
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
                            "weather": w,
                        }
                    else:
                        st.warning("⚠️ AI khong phan hoi. Vui long thu lai.")
                except Exception as e:
                    st.error(f"Loi he thong: {e}")
                    st.info("Kiem tra lai ket noi mang hoac GEMINI_API_KEY.")

    diag = st.session_state.get("last_diagnosis")
    if diag:
        st.markdown("---")
        st.subheader("🔬 Ket qua chan doan")
        st.markdown(diag["result"])

        if diag.get("plant"):
            plant_name = diag["plant"]["name"]
            col_save, col_done = st.columns([3, 2])
            with col_save:
                if st.button(f"💾 Luu chan doan vao nhat ky '{plant_name}'",
                             key="btn_save_diag"):
                    summary = diag["result"][:120].rsplit(" ", 1)[0] + "..."
                    for p in data["plants"]:
                        if p["id"] == diag["plant"]["id"]:
                            p.setdefault("logs", []).append({
                                "d": datetime.now().strftime("%d/%m %H:%M"),
                                "c": f"🩺 AI Chan doan: {summary}"
                            })
                            break
                    save_data(data)
                    del st.session_state["last_diagnosis"]
                    st.success(f"✅ Da luu vao nhat ky **{plant_name}**!")
                    st.rerun()
            with col_done:
                if st.button("✅ Da xu ly xong, luu & dong",
                             key="btn_done_diag", type="primary"):
                    for p in data["plants"]:
                        if p["id"] == diag["plant"]["id"]:
                            p.setdefault("logs", []).append({
                                "d": datetime.now().strftime("%d/%m %H:%M"),
                                "c": "✅ Da xu ly benh theo chi dan cua Bac si AI."
                            })
                            break
                    save_data(data)
                    del st.session_state["last_diagnosis"]
                    st.success("Da ghi nhat ky 'xu ly hoan tat'!")
                    st.rerun()

# =============================================================
# 💬 TRO LY KY THUAT
# =============================================================

elif menu == "💬 Tro ly Ky thuat":
    back_button()
    st.title("💬 Tro ly Ky thuat Nong nghiep")

    city     = weather.get("city", "...")
    temp_now = weather.get("temp", "?")
    hum_now  = weather.get("hum",  "?")
    wind_now = weather.get("wind", "?")
    desc_now = weather.get("desc", "")
    dp       = fetch_disease_pressure(lat, lon)
    risk_icon = RISK_COLOR.get(dp.get("level", "unknown"), "⚪")

    st.caption(
        f"📍 {city} | {temp_now}°C — {hum_now}% am "
        f"— Gio {wind_now} km/h — {desc_now} "
        f"| 🦠 Benh 48h: {risk_icon} {dp.get('level','?').upper()}"
    )

    for chat in data.get("chat_history", []):
        with st.chat_message("user"):
            st.write(chat["user"])
        with st.chat_message("assistant"):
            st.markdown(chat["ai"])

    if prompt := st.chat_input("Hoi AI ve ky thuat vuon, phan bon, sau benh..."):
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("🤖 AI dang phan tich du lieu..."):
            try:
                w_ctx = (
                    f"Nhiet do {temp_now}°C, Do am {hum_now}%, "
                    f"Gio {wind_now} km/h, {desc_now}. "
                    f"Ap luc benh 48h: {dp.get('level','?').upper()} "
                    f"(score {dp.get('score',0)}/100)"
                )
                full_prompt = f"""
Ban la Chuyen gia Nong nghiep Cong nghe cao.
Du lieu thoi tiet hien tai tai {city}: {w_ctx}
Cau hoi cua nong dan: {prompt}

Yeu cau:
- Tra loi bang tieng Viet.
- Tap trung giai phap ky thuat, uu tien huu co/sinh hoc.
- Co tinh den ap luc benh hien tai khi tu van.
- Su dung Markdown (###, **, -) de trinh bay dep mat.
"""
                response = model.generate_content(
                    full_prompt,
                    request_options={"timeout": 30}
                )
                ai_res = (
                    response.text if hasattr(response, "text")
                    else "⚠️ AI khong the tra loi cau hoi nay."
                )

                with st.chat_message("assistant"):
                    st.markdown(ai_res)

                add_chat(data, prompt, ai_res)
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Loi ket noi AI: {e}")
                st.info("Kiem tra lai GEMINI_API_KEY trong file secrets.")
