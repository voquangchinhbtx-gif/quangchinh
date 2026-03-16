import streamlit as st
import requests
import math
import google.generativeai as genai
from PIL import Image
from datetime import datetime
# ✅ FIX: thêm save_data vào import
from database import load_data, save_data, add_plant, delete_plant, add_chat
from weather import get_weather

# =========================
# CẤU HÌNH
# =========================

try:
    API_KEY = st.secrets["OPENWEATHER_API_KEY"]
    LAT     = st.secrets.get("LAT", 16.4637)
    LON     = st.secrets.get("LON", 107.5909)
except:
    # ✅ FIX: không hardcode key thật
    API_KEY = ""
    LAT, LON = 16.4637, 107.5909

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
        "Hữu cơ (Ưu tiên)": "Phân gà oai, Đạm cá, Humic Acid, Dịch chuối, Phân trùn quế.",
        "Vô cơ (Bổ sung)":  "NPK 20-20-15, Kali Sunfat."
    },
    "Trị bệnh": {
        "Sinh học (Ưu tiên)":      "Trichoderma, Nano Bạc, Tinh dầu thảo mộc, Bordeaux.",
        "Hóa học (Khi bệnh nặng)": "Metalaxyl, Validamycin."
    },
    "Trị côn trùng": {
        "Sinh học (Ưu tiên)":     "BT, Dịch tỏi ớt, Nấm xanh Metarhizium.",
        "Hóa học (Khi bùng dịch)": "Abamectin."
    }
}

# =========================
# TRI THỨC CÂY TRỒNG
# =========================

CROP_KNOWLEDGE = {
    "Ớt Aji Charapita": [
        {
            "stage":   "Cây con",
            "days":    (0, 20),
            "organic": "Tưới Humic + Trichoderma để kích rễ.",
            "backup":  "Nếu cây héo rũ, dùng Metalaxyl tưới gốc.",
            "note":    "Phủ gốc bằng xơ dừa để giữ ẩm."
        },
        {
            "stage":   "Phát triển lá",
            "days":    (21, 60),
            "organic": "Phun đạm cá + dịch tỏi ớt ngừa sâu.",
            "backup":  "Nếu bọ trĩ bùng phát, dùng Abamectin liều nhẹ.",
            "note":    "Bấm ngọn để cây phân cành."
        },
        {
            "stage":   "Ra hoa / Trái",
            "days":    (61, 150),
            "organic": "Bón phân trùn quế + dịch chuối.",
            "backup":  "Nếu rụng hoa, bổ sung Canxi-Bo.",
            "note":    "Không tưới đẫm buổi tối."
        }
    ],
    "Chung": [
        {
            "stage":   "Cây non",
            "days":    (0, 30),
            "organic": "Tưới Humic + Trichoderma kích rễ.",
            "backup":  "Nếu héo rũ dùng Metalaxyl nhẹ.",
            "note":    "Giữ ẩm đất, tránh nắng gắt."
        },
        {
            "stage":   "Sinh trưởng",
            "days":    (31, 90),
            "organic": "Bón phân hữu cơ hoai + đạm cá.",
            "backup":  "Nếu sâu ăn lá dùng BT.",
            "note":    "Theo dõi côn trùng định kỳ."
        },
        {
            "stage":   "Ra hoa / kết trái",
            "days":    (91, 200),
            "organic": "Bổ sung Kali + dịch chuối.",
            "backup":  "Nếu rụng hoa bổ sung Canxi-Bo.",
            "note":    "Không tưới quá nhiều nước."
        }
    ]
}

# =========================
# AI CẢNH BÁO và CHẨN ĐOÁN
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
# HELPER: weather string an toàn
# =========================

def safe_weather_str(w):
    if not w:
        return "N/A"
    temp = w.get("temp", "?")
    hum  = w.get("hum",  "?")
    return f"{temp}°C, {hum}% ẩm"

# =========================
# LẤY THỜI TIẾT (CACHE)
# =========================

@st.cache_data(ttl=600)
def fetch_weather_data():
    return get_weather()

# =========================
# STREAMLIT CONFIG
# =========================

st.set_page_config(
    page_title="Aji Farm Pro",
    layout="wide",
    page_icon="🌶️"
)

# ✅ FIX: load_data() và weather chỉ gọi 1 lần duy nhất
data    = load_data()
weather = fetch_weather_data()

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
            "📸 Camera Chẩn đoán",
            "💬 AI Assistant"
        ]
    )

# =========================
# DASHBOARD
# =========================

if menu == "📊 Dashboard Chuyên sâu":
    st.title("📊 Quan trắc VPD & Thời tiết")

    if weather:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Nhiệt độ", f"{weather['temp']}°C")
        c2.metric("Độ ẩm",    f"{weather['hum']}%")
        c3.metric("Mưa",      f"{weather['rain']}mm")
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
# QUẢN LÝ CÂY TRỒNG
# =========================

# ✅ FIX: đổi if → elif để tránh chạy đồng thời nhiều menu
elif menu == "🌱 Quản lý Cây trồng":
    st.title("🌱 Quản lý Vườn & Hệ thống Tối ưu AI")

    # ------------------------------------------------------------------ #
    # 1. KHUNG QUẢN TRỊ: THÊM & SỬA
    # ------------------------------------------------------------------ #
    with st.expander("⚙️ Thiết lập & Quản lý danh sách cây", expanded=False):
        tab_add, tab_edit = st.tabs(["➕ Thêm cây mới", "✏️ Chỉnh sửa thông tin"])

        with tab_add:
            c1, c2 = st.columns(2)
            with c1:
                name_in = st.text_input(
                    "Tên định danh cây",
                    placeholder="Ví dụ: Ớt Aji - Lứa 01",
                    key="add_name"
                )
            with c2:
                type_in = st.text_input(
                    "Loại cây cụ thể",
                    placeholder="Ví dụ: Ớt Aji Charapita",
                    key="add_type"
                )

            date_in = st.date_input("Ngày trồng thực tế", value=datetime.now(), key="add_date")

            if st.button("🚀 Khởi tạo vườn", key="btn_init_farm"):
                if name_in.strip() and type_in.strip():
                    full_id = f"{name_in} | {type_in}"
                    data    = add_plant(data, full_id, date_in.strftime("%Y-%m-%d"))
                    save_data(data)
                    st.success(f"Đã thêm **{name_in}** vào hệ thống!")
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

                # ✅ guard parse date an toàn
                try:
                    edit_date_val = datetime.strptime(p_edit["date"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    edit_date_val = datetime.now()

                new_d = st.date_input("Sửa ngày trồng", value=edit_date_val, key="edit_date")

                if st.button("💾 Lưu cập nhật", key="btn_update"):
                    for p in data["plants"]:
                        if p["id"] == p_edit["id"]:
                            p["name"] = new_n
                            p["date"] = new_d.strftime("%Y-%m-%d")
                    save_data(data)
                    st.success("Đã cập nhật!")
                    st.rerun()
            else:
                st.info("Chưa có cây nào để sửa.")

    # ------------------------------------------------------------------ #
    # 2. DANH SÁCH CÂY & QUY TRÌNH TỐI ƯU
    # ------------------------------------------------------------------ #
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

                    # ✅ guard parse date
                    try:
                        plant_date = datetime.strptime(p["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        plant_date = datetime.now()

                    age = max((datetime.now() - plant_date).days, 0)
                    st.write(f"⏱️ **{age} ngày tuổi**")
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
                        # ✅ list() trước reversed để slice được
                        recent_logs = list(reversed(p.get("logs", [])))[:3]
                        if recent_logs:
                            for log in recent_logs:
                                st.caption(f"📅 {log['d']}: {log['c']}")
                        else:
                            st.caption("Chưa có nhật ký nào.")

                # ---- CỘT CHĂM SÓC / AI ---- #
                with col_care:
                    # ✅ giới hạn split 1 lần tránh edge case
                    parts     = p["name"].split("|", 1)
                    crop_type = parts[1].strip() if len(parts) > 1 else parts[0].strip()

                    st.markdown(f"📋 **Phác đồ tối ưu AI cho: {crop_type}**")

                    if st.button("🧠 AI: Tối ưu 15 ngày tới", key=f"btn_opt_{p['id']}"):
                        with st.spinner("Đang phân tích nhật ký & dữ liệu mở..."):
                            try:
                                model   = genai.GenerativeModel("gemini-1.5-flash")
                                history = " | ".join([l["c"] for l in p.get("logs", [])])
                                w_info  = safe_weather_str(weather)

                                prompt = f"""
Bạn là chuyên gia nông nghiệp hữu cơ thực chiến. Trả lời BẰNG TIẾNG VIỆT.
Thông tin cây: {crop_type}, {age} ngày tuổi. Thời tiết hiện tại: {w_info}.
Nhật ký thực tế: {history if history else "Chưa có dữ liệu"}.

NHIỆM VỤ: Lập quy trình chăm sóc 15 ngày tới, trình bày theo đúng format sau:

### 🌿 DINH DƯỠNG
- Ưu tiên phân hữu cơ: [tên, liều lượng, tần suất]
- Phân vô cơ dự phòng (nếu cần): [tên, liều lượng]

### 🛡️ BẢO VỆ THỰC VẬT
- Sinh học ưu tiên: [tên sản phẩm, cách dùng]
- Hóa học dự phòng (nếu bùng phát): [tên, liều lượng]

### 🔧 ĐIỀU CHỈNH TỪ NHẬT KÝ
- [Phân tích lỗi chăm sóc nếu có, hoặc ghi "Không có vấn đề cần điều chỉnh"]

### 📅 LỊCH 15 NGÀY
| Ngày  | Việc cần làm |
|-------|-------------|
| 1-5   | ... |
| 6-10  | ... |
| 11-15 | ... |

Giữ ngắn gọn, thực tế, tránh lý thuyết chung chung.
"""
                                res         = model.generate_content(prompt)
                                recipe_text = getattr(res, "text", None)

                                if recipe_text:
                                    p["optimized_recipe"] = recipe_text
                                    save_data(data)
                                    st.session_state[f"st_view_{p['id']}"] = recipe_text
                                else:
                                    st.warning("AI không trả về kết quả. Vui lòng thử lại.")

                            except Exception as e:
                                st.error(f"Lỗi kết nối AI: {e}")

                    plan_display = st.session_state.get(
                        f"st_view_{p['id']}",
                        p.get("optimized_recipe")
                    )
                    if plan_display:
                        with st.expander("📍 XEM QUY TRÌNH ĐÃ LƯU", expanded=True):
                            st.markdown(plan_display)
                    else:
                        st.caption("Chưa có quy trình tối ưu. Hãy nhấn nút AI.")

                # ---- CỘT THAO TÁC ---- #
                with col_action:
                    st.caption("⚙️ Thao tác")

                    with st.popover("🗑️ Kết thúc vụ"):
                        st.warning(f"Xác nhận gỡ **{p['name']}** khỏi vườn?")
                        if st.button("✔️ Xác nhận xoá", key=f"btn_del_{p['id']}", type="primary"):
                            data = delete_plant(data, p["id"])
                            save_data(data)
                            st.rerun()

                    if weather:
                        # ✅ guard từng field riêng
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
    st.title("📸 Bác sĩ AI: Phân lập & Chẩn đoán")

    st.info("""
    💡 **Hướng dẫn chụp ảnh:**
    1. Đảm bảo đủ ánh sáng để AI thấy rõ màu sắc lá.
    2. Chụp cận cảnh vết bệnh, sâu hại hoặc mặt dưới của lá.
    3. Nếu có thể, hãy để một phần lá lành trong khung hình để AI đối chiếu.
    """)

    # ------------------------------------------------------------------ #
    # CHỌN CÂY & CHỤP ẢNH
    # ------------------------------------------------------------------ #
    plants_list = data.get("plants", [])
    selected_p  = None

    if plants_list:
        selected_p = st.selectbox(
            "Chọn cây cần chẩn đoán:",
            plants_list,
            format_func=lambda x: x["name"],
            key="sb_cam"
        )
    else:
        st.info("🌵 Chưa có cây nào trong vườn. Hãy thêm cây ở mục Quản lý Cây trồng trước.")

    img_file = st.camera_input("Chụp ảnh bộ phận nghi ngờ bệnh")

    if img_file:
        image = Image.open(img_file)
        st.image(image, width=450, caption="Dữ liệu hình ảnh")

        # ------------------------------------------------------------------ #
        # NÚT CHẨN ĐOÁN
        # ------------------------------------------------------------------ #
        if st.button("🚀 Bắt đầu Xét nghiệm AI", key="btn_cam_ai"):
            with st.spinner("Đang phân lập Vi khuẩn, Virus, Nấm, Sâu bọ..."):
                try:
                    model = genai.GenerativeModel("gemini-1.5-flash")

                    # Chuẩn bị context thời tiết an toàn
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
                        w_info = "Không có dữ liệu thời tiết (ngoại tuyến). AI chỉ dựa trên hình ảnh."

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
**Tên khoa học:** [Bắt buộc nếu xác định được — ví dụ: *Phytophthora infestans*, *Botrytis cinerea*...]
**Tên thường gọi:** [Ví dụ: Mốc sương, Thán thư, Héo xanh vi khuẩn...]
**Bằng chứng visual:** [Mô tả chính xác màu sắc, hình dạng, vị trí vết bệnh trong ảnh]

---

### 🔬 PHÂN TÍCH SÂU TÁC NHÂN

🍄 **Nếu là Nấm — xác định:**
- Nhóm nấm: [Oomycete / Ascomycete / Basidiomycete / Deuteromycete]
- Cơ chế lây lan: [Bào tử khí / Đất / Nước / Tiếp xúc]
- Điều kiện bùng phát: [Nhiệt độ, độ ẩm thuận lợi]
- Giai đoạn bệnh: [Sơ nhiễm / Phát triển / Nặng]

🧫 **Nếu là Vi khuẩn — xác định:**
- Chi/Loài: [*Xanthomonas* / *Pseudomonas* / *Erwinia* / *Ralstonia*...]
- Dạng triệu chứng: [Đốm góc cạnh / Thối nhũn / Héo mạch dẫn / Sùi loét]
- Vector lây truyền: [Nước mưa / Côn trùng / Dụng cụ / Vết thương cơ học]

🧬 **Nếu là Virus — xác định:**
- Họ virus nghi ngờ: [Potyvirus / Tobamovirus / Begomovirus / Cucumovirus...]
- Triệu chứng điển hình: [Khảm / Xoăn lá / Vàng gân / Còi cọc]
- Vector chính: [Bọ trĩ / Rệp / Bọ phấn / Tuyến trùng]

🐛 **Nếu là Sâu bọ — xác định:**
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
                    # ✅ encode ảnh đúng format cho Gemini API
                    img_bytes  = img_file.getvalue()
                    image_part = {
                        "mime_type": "image/jpeg",
                        "data":      img_bytes
                    }

                    res    = model.generate_content([prompt, image_part])
                    result = getattr(res, "text", None)

                    if result:
                        # ✅ lưu session_state để không mất sau rerun
                        st.session_state["last_diagnosis"] = {
                            "result":   result,
                            "plant_id": selected_p["id"] if selected_p else None,
                        }
                    else:
                        st.warning("⚠️ AI không phản hồi. Vui lòng thử lại.")

                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")
                    st.info("Kiểm tra lại kết nối mạng hoặc API Key Gemini.")

        # ------------------------------------------------------------------ #
        # HIỂN THỊ KẾT QUẢ — nằm NGOÀI block spinner, render độc lập
        # ------------------------------------------------------------------ #
        diag = st.session_state.get("last_diagnosis")

        if diag:
            st.markdown("---")
            st.subheader("🔬 Kết quả chẩn đoán")
            st.markdown(diag["result"])

            # ✅ nút lưu nằm NGOÀI block chẩn đoán
            if selected_p:
                if st.button("📥 Lưu chẩn đoán vào Nhật ký cây", key="btn_save_diag"):
                    # ✅ cắt đẹp theo từ, không cắt giữa chừng
                    summary = diag["result"]
                    if len(summary) > 120:
                        summary = summary[:120].rsplit(" ", 1)[0] + "..."

                    # ✅ tìm đúng object trong data["plants"] để sửa
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
    st.title("💬 Trợ lý Kỹ thuật")

    if weather and isinstance(weather, dict):
        st.caption(f"📍 Bối cảnh thực địa: {weather.get('temp','?')}°C - {weather.get('hum','?')}% ẩm")
    else:
        st.caption("⚠️ Chế độ ngoại tuyến: AI không có dữ liệu thời tiết.")

    # 1. KHUNG LỊCH SỬ CHAT
    chat_container = st.container()
    with chat_container:
        for chat in data.get("chat_history", []):
            with st.chat_message("user"):
                st.write(chat["user"])
            with st.chat_message("assistant"):
                st.markdown(chat["ai"])

    # 2. XỬ LÝ NHẬP LIỆU
    if prompt := st.chat_input("Hỏi AI về kỹ thuật vườn, phân bón, sâu bệnh..."):
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("🤖 AI đang phân tích dữ liệu..."):
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")

                w_ctx = (
                    f"Nhiệt độ {weather.get('temp','?')}°C, Độ ẩm {weather.get('hum','?')}%"
                    if isinstance(weather, dict)
                    else "Không có dữ liệu thời tiết thực địa"
                )

                full_prompt = f"""
Bạn là Chuyên gia Nông nghiệp Công nghệ cao.
Dữ liệu thời tiết hiện tại: {w_ctx}
Câu hỏi của nông dân: {prompt}

Yêu cầu:
- Trả lời bằng tiếng Việt.
- Tập trung giải pháp kỹ thuật, ưu tiên hữu cơ/sinh học.
- Sử dụng Markdown (###, **, -) để trình bày đẹp mắt.
- Tuyệt đối không nhắc đến việc soạn giáo án hay giảng dạy.
"""
                response = model.generate_content(full_prompt)
                ai_res   = (
                    response.text
                    if hasattr(response, "text")
                    else "⚠️ AI không thể trả lời câu hỏi này. Vui lòng hỏi về kỹ thuật nông nghiệp."
                )

                with st.chat_message("assistant"):
                    st.markdown(ai_res)

                # 3. LƯU VÀO DATABASE
                add_chat(data, prompt, ai_res)
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Lỗi kết nối AI: {e}")
                st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets của bạn.")
