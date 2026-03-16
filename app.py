import streamlit as st
import math
import re
import google.generativeai as genai
from PIL import Image
from datetime import datetime
from database import load_data, save_data, add_plant, delete_plant, add_chat, get_crop_history, archive_and_delete_plant
from streamlit_js_eval import get_geolocation

# =========================
# CẤU HÌNH
# =========================

try:
    GENAI_KEY = st.secrets["GEMINI_API_KEY"]
except:
    GENAI_KEY = ""

genai.configure(api_key=GENAI_KEY)

# =========================
# DANH MỤC VẬT TƯ
# =========================

FARM_RESOURCES = {
    "Dinh dưỡng": {
        "Hữu cơ (Ưu tiên)": "Phân gà hoai, Đạm cá, Humic Acid, Dịch chuối, Phân trùn quế.",
        "Vô cơ (Bổ sung)":  "NPK 20-20-15, Kali Sunfat."
    },
    "Trị bệnh": {
        "Sinh học (Ưu tiên)":      "Trichoderma, Nano Bạc, Tinh dầu thảo mộc, Bordeaux.",
        "Hóa học (Khi bệnh nặng)": "Metalaxyl, Validamycin."
    },
    "Trị côn trùng": {
        "Sinh học (Ưu tiên)":      "BT, Dịch tỏi ớt, Nấm xanh Metarhizium.",
        "Hóa học (Khi bùng dịch)": "Abamectin."
    }
}

# =========================
# TRI THỨC CÂY TRỒNG
# =========================

CROP_KNOWLEDGE = {
    "Ớt Aji Charapita": [
        {"stage": "Cây con",       "days": (0,20),   "organic": "Tưới Humic + Trichoderma để kích rễ.",     "backup": "Nếu cây héo rũ, dùng Metalaxyl tưới gốc.",        "note": "Phủ gốc bằng xơ dừa để giữ ẩm."},
        {"stage": "Phát triển lá", "days": (21,60),  "organic": "Phun đạm cá + dịch tỏi ớt ngừa sâu.",     "backup": "Nếu bọ trĩ bùng phát, dùng Abamectin liều nhẹ.", "note": "Bấm ngọn để cây phân cành."},
        {"stage": "Ra hoa / Trái", "days": (61,150), "organic": "Bón phân trùn quế + dịch chuối.",          "backup": "Nếu rụng hoa, bổ sung Canxi-Bo.",                 "note": "Không tưới đẫm buổi tối."}
    ],
    "Chung": [
        {"stage": "Cây non",           "days": (0,30),   "organic": "Tưới Humic + Trichoderma kích rễ.",   "backup": "Nếu héo rũ dùng Metalaxyl nhẹ.",   "note": "Giữ ẩm đất, tránh nắng gắt."},
        {"stage": "Sinh trưởng",       "days": (31,90),  "organic": "Bón phân hữu cơ hoai + đạm cá.",     "backup": "Nếu sâu ăn lá dùng BT.",           "note": "Theo dõi côn trùng định kỳ."},
        {"stage": "Ra hoa / kết trái", "days": (91,200), "organic": "Bổ sung Kali + dịch chuối.",          "backup": "Nếu rụng hoa bổ sung Canxi-Bo.",   "note": "Không tưới quá nhiều nước."}
    ]
}

# =========================
# DANH SÁCH CÂY TRỒNG
# =========================

CROP_LIST = [
    "Ớt Aji Charapita",
    "Ớt Hiểm",
    "Ớt Chuông",
    "Cà chua Cherry",
    "Cà chua Beef",
    "Dưa leo",
    "Dưa lưới",
    "Cà tím",
    "Bắp cải",
    "Xà lách",
    "Rau muống",
    "Húng quế",
    "Cần tây",
    "Khác (nhập tay)"
]

# =========================
# AI CẢNH BÁO
# =========================

def ai_crop_warning(stage, weather):
    if not weather:
        return None
    temp = weather["temp"]
    hum  = weather["hum"]
    rain = weather["rain"]
    if hum > 85:
        return "🦠 Độ ẩm cao → nguy cơ nấm bệnh. Khuyến nghị: Trichoderma hoặc Nano Bạc."
    if temp > 32 and hum < 50:
        return "🌵 Trời nóng khô → Nguy cơ bùng phát Bọ trĩ & Nhện đỏ."
    if temp > 34:
        return "🔥 Nhiệt độ cao → cây dễ sốc nhiệt. Nên tăng tưới và che nắng."
    if stage == "Phát triển lá" and rain > 0:
        return "🐛 Sau mưa cây ra chồi non → Dễ bị sâu khoang tấn công."
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
# HELPER
# =========================

def safe_weather_str(w):
    if not w:
        return "N/A"
    return f"{w.get('temp','?')}°C, {w.get('hum','?')}% ẩm"

def build_season_context(history):
    if not history:
        return "Chưa có dữ liệu vụ trước."
    lines = []
    for i, s in enumerate(history[-3:], 1):
        lines.append(f"--- Vụ {i} ({s.get('date_start','')} → {s.get('date_end','')}) ---")
        logs = s.get("logs", [])
        if logs:
            log_texts = [f"{l.get('d', l.get('date',''))}: {l.get('c', l.get('content',''))}" for l in logs[-10:]]
            lines.append("Nhật ký: " + " | ".join(log_texts))
        recipe = s.get("recipe", "")
        if recipe:
            lines.append(f"Quy trình AI vụ đó: {recipe[:300]}...")
    return "\n".join(lines)

# =========================
# STREAMLIT CONFIG
# =========================

st.set_page_config(page_title="Aji Farm Pro", layout="wide", page_icon="🌶️")

# =========================
# 📍 LẤY GPS TỪ TRÌNH DUYỆT
# =========================

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

# =========================
# LẤY THỜI TIẾT (CACHE)
# =========================

from weather import get_weather

@st.cache_data(ttl=600)
def fetch_weather_data(lat, lon):
    return get_weather(lat=lat, lon=lon)

data    = load_data()
weather = fetch_weather_data(st.session_state["gps_lat"], st.session_state["gps_lon"])

# =========================
# SIDEBAR
# =========================

with st.sidebar:
    st.title("🌶️ Aji Farm AI")
    if weather:
        st.caption(f"📍 {weather.get('city', 'Vị trí của bạn')}")

    menu_options = [
        "📊 Dashboard Chuyên sâu",
        "🌱 Quản lý Cây trồng",
        "📸 Camera Chẩn đoán",
        "💬 AI Assistant"
    ]

    default_idx = 0
    if "menu_choice" in st.session_state and st.session_state["menu_choice"] in menu_options:
        default_idx = menu_options.index(st.session_state["menu_choice"])

    menu = st.radio("Menu", menu_options, index=default_idx, key="menu_radio")

    # ✅ Lưu menu trước đó
    if "current_menu" not in st.session_state:
        st.session_state["current_menu"] = menu
    if st.session_state["current_menu"] != menu:
        st.session_state["prev_menu"]    = st.session_state["current_menu"]
        st.session_state["current_menu"] = menu
    st.session_state["menu_choice"] = menu

# =========================
# HELPER: NÚT BACK ĐẦU TRANG
# =========================

def back_button():
    if "prev_menu" in st.session_state:
        if st.button("⬅️ Quay lại"):
            st.session_state["menu_choice"] = st.session_state["prev_menu"]
            st.rerun()

# =========================
# DASHBOARD
# =========================

if menu == "📊 Dashboard Chuyên sâu":
    back_button()
    st.title("📊 Quan trắc VPD & Thời tiết")
    if weather:
        city = weather.get("city", "Vị trí của bạn")
        st.markdown(f"📍 **{city}**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Nhiệt độ",  f"{weather['temp']}°C")
        c2.metric("Độ ẩm",     f"{weather['hum']}%")
        c3.metric("Mưa",       f"{weather['rain']}mm")
        c4.metric("Thời tiết", weather['desc'].capitalize())
        vpd = calculate_vpd(weather['temp'], weather['hum'])
        st.markdown(f"### Chỉ số VPD: `{vpd:.2f} kPa`")
        if vpd < 0.5:
            st.error("Nguy cơ nấm bệnh cao")
        elif vpd > 2:
            st.warning("Không khí khô")
        else:
            st.success("Điều kiện sinh trưởng tốt")
        warnings = weather.get("agri_warnings", [])
        if warnings:
            st.markdown("### 🚨 Cảnh báo Nông nghiệp")
            for w in warnings:
                st.info(w)
    else:
        st.error("Không lấy được dữ liệu thời tiết")

# =========================
# QUẢN LÝ CÂY TRỒNG
# =========================

elif menu == "🌱 Quản lý Cây trồng":
    back_button()
    st.title("🌱 Quản lý Vườn & Hệ thống Tối ưu AI")

    with st.expander("⚙️ Thiết lập & Quản lý danh sách cây", expanded=False):
        tab_add, tab_edit = st.tabs(["➕ Thêm cây mới", "✏️ Chỉnh sửa thông tin"])

        with tab_add:
            # ── CHỌN LOẠI CÂY ──
            crop_select = st.selectbox("🌿 Chọn loại cây trồng", CROP_LIST, key="crop_select")
            if crop_select == "Khác (nhập tay)":
                type_in = st.text_input(
                    "Nhập tên loại cây (không có trong danh sách)",
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
                date_seed_soak  = st.date_input("🫧 Ngày ủ hạt",          value=datetime.now(), key="date_seed_soak")
                date_transplant = st.date_input("🌱 Ngày trồng xuống đất", value=datetime.now(), key="date_transplant")
            with c2:
                date_seedling = st.date_input("🌿 Ngày gieo ươm", value=datetime.now(), key="date_seedling")
                st.caption("🍅 Ngày thu hoạch dự kiến sẽ do AI tự tính sau khi tạo quy trình chuẩn.")

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
                    st.success(f"Đã thêm **{name_in}** vào hệ thống! Hãy nhấn **🌱 Tạo quy trình chuẩn** để AI tính ngày thu hoạch.")
                    st.rerun()
                else:
                    st.warning("Vui lòng điền đủ Tên và Loại cây.")

        with tab_edit:
            all_p = data.get("plants", [])
            if all_p:
                p_edit = st.selectbox(
                    "Chọn cây muốn sửa",
                    all_p,
                    format_func=lambda x: x["name"],
                    key="sb_edit"
                )
                new_n = st.text_input("Sửa tên định danh", value=p_edit["name"], key="edit_name")

                st.markdown("##### 📅 Các mốc thời gian")
                c1, c2 = st.columns(2)
                with c1:
                    try:
                        val_seed_soak = datetime.strptime(p_edit["date_seed_soak"], "%Y-%m-%d") if p_edit.get("date_seed_soak") else datetime.now()
                    except (ValueError, TypeError):
                        val_seed_soak = datetime.now()
                    new_seed_soak = st.date_input("🫧 Ngày ủ hạt", value=val_seed_soak, key="edit_seed_soak")

                    try:
                        val_transplant = datetime.strptime(p_edit["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        val_transplant = datetime.now()
                    new_d = st.date_input("🌱 Ngày trồng xuống đất", value=val_transplant, key="edit_date")

                with c2:
                    try:
                        val_seedling = datetime.strptime(p_edit["date_seedling"], "%Y-%m-%d") if p_edit.get("date_seedling") else datetime.now()
                    except (ValueError, TypeError):
                        val_seedling = datetime.now()
                    new_seedling = st.date_input("🌿 Ngày gieo ươm", value=val_seedling, key="edit_seedling")

                    harvest_date = p_edit.get("date_harvest") or "Chưa có (AI sẽ tự tính)"
                    st.text_input(
                        "🍅 Dự kiến thu hoạch (do AI tính)",
                        value=harvest_date,
                        disabled=True,
                        key="edit_harvest_display"
                    )

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

                # ---- CỘT THÔNG TIN ---- #
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
                            "Hôm nay có gì mới? (Bón phân, tình trạng cây...)",
                            key=f"log_area_{p['id']}"
                        )
                        if st.button("Lưu nhật ký", key=f"btn_log_{p['id']}"):
                            if log_text.strip():
                                if "logs" not in p:
                                    p["logs"] = []
                                p["logs"].append({
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

                # ---- CỘT CHĂM SÓC / AI ---- #
                with col_care:
                    parts     = p["name"].split("|", 1)
                    crop_type = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    st.markdown(f"📋 **Phác đồ tối ưu AI cho: {crop_type}**")

                    # ✅ NÚT 1: Tạo quy trình chuẩn + AI tự tính ngày thu hoạch
                    if st.button("🌱 Tạo quy trình chuẩn", key=f"btn_std_{p['id']}"):
                        with st.spinner("AI đang tạo quy trình chuẩn & tính ngày thu hoạch..."):
                            try:
                                model  = genai.GenerativeModel("gemini-2.0-flash")
                                w_info = safe_weather_str(weather)

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
                                res = model.generate_content(
                                    std_prompt,
                                    request_options={"timeout": 30}
                                )
                                std_text = getattr(res, "text", None)
                                if std_text:
                                    p["standard_recipe"] = std_text
                                    # ✅ AI tự parse ngày thu hoạch
                                    match = re.search(r"Ngày thu hoạch dự kiến:\s*(\d{4}-\d{2}-\d{2})", std_text)
                                    if match:
                                        p["date_harvest"] = match.group(1)
                                    save_data(data)
                                    st.session_state[f"std_view_{p['id']}"] = std_text
                                    st.rerun()
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    std_display = st.session_state.get(f"std_view_{p['id']}", p.get("standard_recipe"))
                    if std_display:
                        with st.expander("📋 XEM QUY TRÌNH CHUẨN", expanded=False):
                            st.markdown(std_display)

                    st.divider()

                    # ✅ NÚT 2: Phân tích tình trạng hôm nay
                    if st.button("🔍 Phân tích tình trạng hôm nay", key=f"btn_analyze_{p['id']}"):
                        with st.spinner("AI đang phân tích tình trạng & đưa ra hướng xử lý..."):
                            try:
                                model         = genai.GenerativeModel("gemini-2.0-flash")
                                w_info        = safe_weather_str(weather)
                                current_logs  = " | ".join([l["c"] for l in p.get("logs", [])])
                                warnings_list = weather.get("agri_warnings", []) if weather else []

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
Dựa trên tình trạng thực tế, đưa ra hướng xử lý CỤ THỂ cho hôm nay và 7 ngày tới:

### 🌡️ ĐÁNH GIÁ TÌNH TRẠNG HIỆN TẠI
- Cây đang ở giai đoạn sinh trưởng nào?
- Những vấn đề nguy cơ từ thời tiết và nhật ký?

### 💊 PHÂN BÓN CẦN BỔ SUNG NGAY
| Loại phân | Liều lượng | Cách bón | Thời điểm |
|-----------|-----------|----------|-----------|
| ...       | ...       | ...      | ...       |

### 🛡️ PHÒNG TRỊ SÂU BỆNH
| Đối tượng | Dấu hiệu cần theo dõi | Xử lý sinh học | Xử lý hóa học |
|-----------|----------------------|----------------|----------------|
| Nấm bệnh  | ...                  | ...            | ...            |
| Côn trùng | ...                  | ...            | ...            |
| Virus     | ...                  | ...            | ...            |

### 📅 LỊCH VIỆC LÀM 7 NGÀY TỚI
| Ngày | Việc cần làm | Lưu ý |
|------|-------------|-------|
| 1-2  | ...         | ...   |
| 3-4  | ...         | ...   |
| 5-7  | ...         | ...   |

### ⚡ HÀNH ĐỘNG NGAY HÔM NAY
[Liệt kê 2-3 việc quan trọng nhất cần làm ngay hôm nay]
"""
                                res = model.generate_content(
                                    analyze_prompt,
                                    request_options={"timeout": 30}
                                )
                                analyze_text = getattr(res, "text", None)
                                if analyze_text:
                                    p["daily_analysis"] = analyze_text
                                    save_data(data)
                                    st.session_state[f"analyze_view_{p['id']}"] = analyze_text
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi AI: {e}")

                    analyze_display = st.session_state.get(f"analyze_view_{p['id']}", p.get("daily_analysis"))
                    if analyze_display:
                        with st.expander("🔍 KẾT QUẢ PHÂN TÍCH HÔM NAY", expanded=True):
                            st.markdown(analyze_display)

                    st.divider()

                    # ✅ NÚT 3: Tối ưu 15 ngày tới
                    if st.button("🧠 AI: Tối ưu 15 ngày tới", key=f"btn_opt_{p['id']}"):
                        with st.spinner("Đang tổng hợp lịch sử & phân tích chuyên sâu..."):
                            try:
                                model        = genai.GenerativeModel("gemini-2.0-flash")
                                w_info       = safe_weather_str(weather)
                                current_logs = " | ".join([l["c"] for l in p.get("logs", [])])
                                past_seasons = get_crop_history(data, crop_type)
                                season_ctx   = build_season_context(past_seasons)
                                season_count = len(past_seasons)

                                prompt = f"""
Bạn là chuyên gia nông nghiệp hữu cơ cấp cao với khả năng học hỏi từ dữ liệu thực địa.
Trả lời BẰNG TIẾNG VIỆT.

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
Dựa trên toàn bộ dữ liệu trên, tạo quy trình chăm sóc tối ưu 15 ngày tới:

### 📊 PHÂN TÍCH GIAI ĐOẠN SINH TRƯỞNG
- Cây đang ở giai đoạn nào?
- Những rủi ro đặc thù của giai đoạn này với thời tiết hiện tại?

### 📊 HỌC TỪ VỤ TRƯỚC
- [Những gì đã hiệu quả cần phát huy]
- [Lỗi/bệnh đã gặp cần phòng tránh chủ động]

### 🌿 DINH DƯỠNG
- Ưu tiên phân hữu cơ: [tên, liều lượng, tần suất]
- Phân vô cơ dự phòng: [tên, liều lượng]

### 🛡️ BẢO VỆ THỰC VẬT
- Sinh học ưu tiên: [tên sản phẩm, cách dùng]
- Hóa học dự phòng: [tên, liều lượng]

### 🔧 ĐIỀU CHỈNH TỪ NHẬT KÝ
- [Phân tích lỗi nếu có, hoặc "Không có vấn đề cần điều chỉnh"]

### 📅 LỊCH 15 NGÀY
| Ngày  | Giai đoạn | Việc cần làm |
|-------|-----------|-------------|
| 1-5   | ...       | ... |
| 6-10  | ...       | ... |
| 11-15 | ...       | ... |

Ngắn gọn, thực tế, bám sát giai đoạn sinh trưởng thực tế của cây.
"""
                                res = model.generate_content(
                                    prompt,
                                    request_options={"timeout": 30}
                                )
                                recipe_text = getattr(res, "text", None)
                                if recipe_text:
                                    p["optimized_recipe"] = recipe_text
                                    save_data(data)
                                    st.session_state[f"st_view_{p['id']}"] = recipe_text
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")
                            except Exception as e:
                                st.error(f"Lỗi kết nối AI: {e}")

                    plan_display = st.session_state.get(f"st_view_{p['id']}", p.get("optimized_recipe"))
                    if plan_display:
                        with st.expander("📍 XEM QUY TRÌNH TỐI ƯU", expanded=False):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chưa có quy trình tối ưu. Hãy nhấn nút AI.")

                # ---- CỘT THAO TÁC ---- #
                with col_action:
                    st.caption("⚙️ Thao tác")
                    with st.popover("🗑️ Kết thúc vụ"):
                        st.warning(f"Kết thúc vụ **{p['name']}**?")
                        st.caption("Nhật ký & quy trình sẽ được lưu lại để AI học cho vụ sau.")
                        if st.button("✔️ Xác nhận", key=f"btn_del_{p['id']}", type="primary"):
                            data = archive_and_delete_plant(data, p["id"])
                            st.rerun()

                    if weather:
                        temp = weather.get("temp")
                        hum  = weather.get("hum")
                        if temp is not None:
                            st.metric("🌡️ Nhiệt độ", f"{temp}°C")
                        if hum is not None:
                            st.metric("💧 Độ ẩm", f"{hum}%")

# =========================
# CAMERA CHẨN ĐOÁN
# =========================

elif menu == "📸 Camera Chẩn đoán":
    back_button()
    st.title("📸 Bác sĩ AI: Phân lập & Chẩn đoán")

    st.info("""
    💡 **Hướng dẫn chụp ảnh:**
    1. Đảm bảo đủ ánh sáng để AI thấy rõ màu sắc lá.
    2. Chụp cận cảnh vết bệnh, sâu hại hoặc mặt dưới của lá.
    3. Nếu có thể, hãy để một phần lá lành trong khung hình để AI đối chiếu.
    """)

    plants_list = data.get("plants", [])
    selected_p  = None

    if plants_list:
        selected_p = st.selectbox("Chọn cây cần chẩn đoán:", plants_list, format_func=lambda x: x["name"], key="sb_cam")
    else:
        st.info("🌵 Chưa có cây nào trong vườn. Hãy thêm cây ở mục Quản lý Cây trồng trước.")

    img_file = st.camera_input("Chụp ảnh bộ phận nghi ngờ bệnh")

    if img_file:
        image = Image.open(img_file)
        st.image(image, width=450, caption="Dữ liệu hình ảnh")

        if st.button("🚀 Bắt đầu Xét nghiệm AI", key="btn_cam_ai"):
            with st.spinner("Đang phân lập Vi khuẩn, Virus, Nấm, Sâu bọ..."):
                try:
                    model = genai.GenerativeModel("gemini-2.0-flash")
                    if weather and isinstance(weather, dict):
                        warnings_list = weather.get("agri_warnings", [])
                        w_info = f"""
THÔNG TIN THỜI TIẾT THỰC ĐỊA:
- Nhiệt độ: {weather.get('temp', 'N/A')}°C
- Độ ẩm: {weather.get('hum', 'N/A')}%
- Bầu trời: {weather.get('desc', 'N/A')}
- Cảnh báo nấm bệnh: {', '.join(warnings_list) if warnings_list else 'Không có'}
"""
                    else:
                        w_info = "Không có dữ liệu thời tiết. AI chỉ dựa trên hình ảnh."

                    prompt = f"""
Bạn là chuyên gia bệnh lý thực vật cấp cao với 20 năm kinh nghiệm thực địa tại Đông Nam Á.
Nhiệm vụ: Phân tích ảnh với độ chính xác của một phòng lab hiện đại.
Dữ liệu môi trường: {w_info}

### NGUYÊN TẮC PHÂN TÍCH:
- KHÔNG được nói "có thể là" hay "có khả năng" — đưa ra chẩn đoán CỤ THỂ nhất có thể dựa trên bằng chứng visual.
- Nếu có nhiều tác nhân, liệt kê TẤT CẢ theo thứ tự khả năng cao → thấp.
- Luôn trích dẫn DẤU HIỆU CỤ THỂ trong ảnh làm bằng chứng cho mỗi chẩn đoán.

Trả lời BẰNG TIẾNG VIỆT theo đúng format:

---

### 🦠 TÁC NHÂN CHÍNH
**Phân loại:** [Nấm / Vi khuẩn / Virus / Sâu bọ / Thiếu dinh dưỡng / Kết hợp]
**Tên khoa học:** [Bắt buộc nếu xác định được]
**Tên thường gọi:** [Ví dụ: Mốc sương, Thán thư, Héo xanh vi khuẩn...]
**Bằng chứng visual:** [Mô tả chính xác màu sắc, hình dạng, vị trí vết bệnh]

---

### 🔬 PHÂN TÍCH SÂU TÁC NHÂN

🍄 **Nếu là Nấm:**
- Nhóm nấm: [Oomycete / Ascomycete / Basidiomycete / Deuteromycete]
- Cơ chế lây lan: [Bào tử khí / Đất / Nước / Tiếp xúc]
- Điều kiện bùng phát: [Nhiệt độ, độ ẩm thuận lợi]
- Giai đoạn bệnh: [Sơ nhiễm / Phát triển / Nặng]

🧫 **Nếu là Vi khuẩn:**
- Chi/Loài: [*Xanthomonas* / *Pseudomonas* / *Erwinia* / *Ralstonia*...]
- Dạng triệu chứng: [Đốm góc cạnh / Thối nhũn / Héo mạch dẫn / Sùi loét]
- Vector lây truyền: [Nước mưa / Côn trùng / Dụng cụ / Vết thương cơ học]

🧬 **Nếu là Virus:**
- Họ virus nghi ngờ: [Potyvirus / Tobamovirus / Begomovirus / Cucumovirus...]
- Triệu chứng điển hình: [Khảm / Xoăn lá / Vàng gân / Còi cọc]
- Vector chính: [Bọ trĩ / Rệp / Bọ phấn / Tuyến trùng]

🐛 **Nếu là Sâu bọ:**
- Bộ/Loài: [Tên khoa học + tên thường gọi]
- Kiểu gây hại: [Chích hút / Gặm nhấm / Đục thân / Cuốn lá]

---

### 🌿 XỬ LÝ SINH HỌC (Ưu tiên hàng đầu)
| Sản phẩm | Hoạt chất / Vi sinh | Liều lượng | Cách dùng | Thời điểm |
|----------|-------------------|------------|-----------|-----------|
| ...      | ...               | ...        | ...       | ...       |

---

### ⚗️ HÓA HỌC DỰ PHÒNG (Chỉ khi sinh học thất bại)
| Thuốc | Hoạt chất | Liều lượng | Lưu ý kháng thuốc |
|-------|-----------|------------|-------------------|
| ...   | ...       | ...        | ...               |

---

### 📈 TIÊN LƯỢNG & CẢNH BÁO
- **Mức độ nguy hiểm:** [🟢 Thấp / 🟡 Trung bình / 🔴 Cao / ⛔ Khẩn cấp]
- **Tốc độ lây lan:** [Chậm / Trung bình / Nhanh — lý do]
- **Rủi ro lây sang cây khác:** [Thấp / Cao — con đường lây]
- **Khuyến nghị khẩn:** [Hành động cần làm NGAY trong 24h]
"""
                    img_bytes  = img_file.getvalue()
                    image_part = {"mime_type": "image/jpeg", "data": img_bytes}
                    res        = model.generate_content(
                        [prompt, image_part],
                        request_options={"timeout": 30}
                    )
                    result = getattr(res, "text", None)

                    if result:
                        st.session_state["last_diagnosis"] = {
                            "result":   result,
                            "plant_id": selected_p["id"] if selected_p else None,
                        }
                    else:
                        st.warning("⚠️ AI không phản hồi. Vui lòng thử lại.")

                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")
                    st.info("Kiểm tra lại kết nối mạng hoặc API Key Gemini.")

        diag = st.session_state.get("last_diagnosis")
        if diag:
            st.markdown("---")
            st.subheader("🔬 Kết quả chẩn đoán")
            st.markdown(diag["result"])
            if selected_p:
                if st.button("📥 Lưu chẩn đoán vào Nhật ký cây", key="btn_save_diag"):
                    summary = diag["result"]
                    if len(summary) > 120:
                        summary = summary[:120].rsplit(" ", 1)[0] + "..."
                    for plant in data["plants"]:
                        if plant["id"] == selected_p["id"]:
                            if "logs" not in plant:
                                plant["logs"] = []
                            plant["logs"].append({
                                "d": datetime.now().strftime("%d/%m %H:%M"),
                                "c": f"🩺 AI Chẩn đoán: {summary}"
                            })
                            break
                    save_data(data)
                    del st.session_state["last_diagnosis"]
                    st.success(f"Đã lưu chẩn đoán vào nhật ký **{selected_p['name']}**!")
                    st.rerun()

# =========================
# AI ASSISTANT
# =========================

elif menu == "💬 AI Assistant":
    back_button()
    st.title("💬 Trợ lý Kỹ thuật")

    city     = weather.get("city", "Vị trí của bạn")
    temp_now = weather.get("temp", "?")
    hum_now  = weather.get("hum",  "?")
    desc_now = weather.get("desc", "")
    st.caption(f"📍 {city}: {temp_now}°C — {hum_now}% ẩm — {desc_now}")

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
                model = genai.GenerativeModel("gemini-2.0-flash")
                w_ctx = f"Nhiệt độ {temp_now}°C, Độ ẩm {hum_now}%, Thời tiết: {desc_now}"

                full_prompt = f"""
Bạn là Chuyên gia Nông nghiệp Công nghệ cao.
Dữ liệu thời tiết hiện tại tại {city}: {w_ctx}
Câu hỏi của nông dân: {prompt}

Yêu cầu:
- Trả lời bằng tiếng Việt.
- Tập trung giải pháp kỹ thuật, ưu tiên hữu cơ/sinh học.
- Sử dụng Markdown (###, **, -) để trình bày đẹp mắt.
- Tuyệt đối không nhắc đến việc soạn giáo án hay giảng dạy.
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
                st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets của bạn.")
