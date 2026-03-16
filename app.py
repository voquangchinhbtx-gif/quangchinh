import streamlit as st
import requests
import math
import google.generativeai as genai
from PIL import Image
from datetime import datetime
from database import load_data, add_plant, delete_plant, add_chat
from weather import get_weather

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
# AI CẢNH BÁO và CHẨN ĐOÁN
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
def fetch_weather_data():
    return get_weather() # Gọi hàm tự định vị từ weather.py

data = load_data()
weather = fetch_weather_data() # Biến 'weather' bây giờ sẽ chứa đầy đủ cảnh báo nấm bệnh


# =========================
# STREAMLIT CONFIG
# =========================

st.set_page_config(
    page_title="Aji Farm Pro",
    layout="wide",
    page_icon="🌶️"
)

data = load_data()

weather = get_weather()


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

if menu == "🌱 Quản lý Cây trồng":
    st.title("🌱 Quản lý Vườn & Hệ thống Tối ưu AI")

    # ------------------------------------------------------------------ #
    # HELPER: lấy weather an toàn
    # ------------------------------------------------------------------ #
    def safe_weather_str(w):
        if not w:
            return "N/A"
        temp = w.get("temp", "?")
        hum  = w.get("hum",  "?")
        return f"{temp}°C, {hum}% ẩm"

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
                    data = add_plant(data, full_id, date_in.strftime("%Y-%m-%d"))
                    save_data(data)  # ✅ persist về DB
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
                    save_data(data)  # ✅ persist về DB
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
                                save_data(data)  # ✅ persist về DB
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
                                w_info  = safe_weather_str(weather)  # ✅ dùng helper

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
                                    save_data(data)  # ✅ persist về DB
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
                            save_data(data)  # ✅ persist về DB
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
# AI CAMERA VÀ AI ASSISTANT
# =========================
elif menu == "📸 Camera Chẩn đoán":
    st.title("📸 Camera Chẩn đoán & Phân tích Thực địa")
    
    # Hướng dẫn chi tiết cho người dùng
    st.info("""
    💡 **Hướng dẫn chụp ảnh:**
    1. Đảm bảo đủ ánh sáng để AI thấy rõ màu sắc lá.
    2. Chụp cận cảnh vết bệnh, sâu hại hoặc mặt dưới của lá.
    3. Nếu có thể, hãy để một phần lá lành trong khung hình để AI đối chiếu.
    """)

    # 1. GIAO DIỆN NHẬN DỮ LIỆU HÌNH ẢNH
    img_file = st.camera_input("Đưa lá cây hoặc sâu hại vào khung hình để chẩn đoán")

    if img_file:
        # Xử lý và hiển thị ảnh đã chụp
        image = Image.open(img_file)
        
        # Hiển thị ảnh trong một khung cố định
        st.image(image, caption="Hình ảnh thực tế đang được phân tích", width=500)

        if st.button("🚀 Bắt đầu Phân tích Chuyên sâu"):
            with st.spinner("🤖 AI đang nhận diện loại cây và đối chiếu dữ liệu môi trường..."):
                try:
                    # Khởi tạo mô hình Gemini 1.5 Flash
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    
                    # 1️⃣ BẢO VỆ BIẾN WEATHER: Chống crash tuyệt đối khi weather = None
                    if weather and isinstance(weather, dict):
                        # Sử dụng .get() để lấy agri_warnings một cách an toàn
                        warnings_list = weather.get('agri_warnings', [])
                        w_info = f"""
                        THÔNG TIN THỜI TIẾT THỰC ĐỊA:
                        - Nhiệt độ đo được: {weather.get('temp', 'N/A')}°C
                        - Độ ẩm không khí: {weather.get('hum', 'N/A')}%
                        - Tình trạng bầu trời: {weather.get('desc', 'N/A')}
                        - Cảnh báo nấm bệnh từ trạm quan trắc: {', '.join(warnings_list) if warnings_list else 'Không có cảnh báo'}
                        """
                    else:
                        w_info = "LƯU Ý: Không có dữ liệu thời tiết thực địa (Chế độ ngoại tuyến), AI sẽ chỉ dựa trên hình ảnh."

                    # 2️⃣ THIẾT LẬP PROMPT KỸ THUẬT (GIỮ NGUYÊN RUỘT CHI TIẾT)
                    prompt = f"""
                    Bạn là một Chuyên gia Bảo vệ Thực vật và Kỹ sư Nông nghiệp Công nghệ cao.
                    Sử dụng dữ liệu môi trường sau đây để tăng độ chính xác cho chẩn đoán:
                    {w_info}

                    Dựa trên hình ảnh lá cây/sâu hại được cung cấp, hãy lập một bản báo cáo kỹ thuật đầy đủ gồm:

                    1. **NHẬN DIỆN CÂY TRỒNG**: Đây chính xác là loại cây gì? (Ví dụ: Ớt Aji Charapita, Cà chua, Hoa hồng...).
                    
                    2. **CHẨN ĐOÁN TÌNH TRẠNG**: 
                       - Tên bệnh hại/Sâu hại/Rối loạn dinh dưỡng.
                       - Mô tả các triệu chứng quan sát được trên ảnh để khẳng định chẩn đoán.

                    3. **PHÂN TÍCH RỦI RO THỜI TIẾT**: 
                       - Giải thích mối liên hệ: Tại sao với nhiệt độ và độ ẩm hiện tại ({weather.get('hum', 'N/A') if weather else 'N/A'}%), tình trạng này lại xuất hiện hoặc có nguy cơ bùng phát mạnh hơn?

                    4. **PHÁC ĐỒ ĐIỀU TRỊ 3 BƯỚC CHUYÊN SÂU**:
                       - **Bước 1 (Xử lý vật lý/Canh tác)**: Cách ly cây, cắt tỉa bộ phận bệnh, hoặc điều chỉnh chế độ tưới tiêu/ánh sáng ngay lập tức.
                       - **Bước 2 (Giải pháp Sinh học/Hữu cơ - Ưu tiên)**: Nêu rõ hoạt chất sinh học (ví dụ: Bacillus thuringiensis, Trichoderma, Nano bạc, Neem oil...) và cách pha chế/phun.
                       - **Bước 3 (Can thiệp Hóa học - Dự phòng cuối)**: Chỉ nêu tên hoạt chất khi bệnh đã ở ngưỡng nguy hiểm (Ví dụ: Metalaxyl, Abamectin, Mancozeb...). Lưu ý liều lượng an toàn cho loại cây này.

                    **YÊU CẦU ĐỊNH DẠNG**: 
                    - Trả lời bằng tiếng Việt.
                    - Định dạng câu trả lời bằng Markdown với các tiêu đề rõ ràng (###), in đậm (**) và danh sách gạch đầu dòng để báo cáo chuyên nghiệp.
                    """

                    # 3️⃣ GỬI DỮ LIỆU ĐA PHƯƠNG THỨC
                    response = model.generate_content([prompt, image])
                    
                    # 4️⃣ BẢO VỆ RESPONSE.TEXT: Tránh lỗi khi AI chặn hoặc trả về rỗng
                    result = response.text if hasattr(response, "text") else "⚠️ AI không thể trích xuất nội dung văn bản. Vui lòng thử chụp lại ảnh rõ hơn."

                    # 5️⃣ HIỂN THỊ KẾT QUẢ
                    st.divider()
                    with st.chat_message("assistant"):
                        st.markdown("### 📝 BÁO CÁO PHÂN TÍCH CHUYÊN GIA")
                        st.markdown(result)
                    
                    st.success("✅ Phân tích hoàn tất. Các đề xuất dựa trên dữ liệu hình ảnh và khí tượng tại chỗ.")
                    
                except Exception as e:
                    st.error(f"⚠️ Hệ thống AI gặp sự cố: {str(e)}")
                    st.info("Kiểm tra lại kết nối mạng hoặc API Key Gemini.")
elif menu == "💬 AI Assistant":
    st.title("💬 Trợ lý Kỹ thuật")

    # Hiển thị bối cảnh thời tiết hiện tại để người dùng biết AI đang dựa trên dữ liệu nào
    if weather and isinstance(weather, dict):
        st.caption(f"📍 Bối cảnh thực địa: {weather.get('temp','?')}°C - {weather.get('hum','?')}% ẩm")
    else:
        st.caption("⚠️ Chế độ ngoại tuyến: AI không có dữ liệu thời tiết.")

    # 1. TẠO KHUNG CUỘN CHO LỊCH SỬ CHAT
    chat_container = st.container()
    
    with chat_container:
        for chat in data.get("chat_history", []):
            with st.chat_message("user"):
                st.write(chat["user"])
            with st.chat_message("assistant"):
                st.markdown(chat["ai"])

    # 2. XỬ LÝ NHẬP LIỆU
    if prompt := st.chat_input("Hỏi AI về kỹ thuật vườn, phân bón, sâu bệnh..."):
        # Hiển thị câu hỏi mới ngay lập tức
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("🤖 AI đang phân tích dữ liệu..."):
            try:
                # Cấu hình mô hình
                model = genai.GenerativeModel("gemini-1.5-flash")

                # Chuẩn bị ngữ cảnh thời tiết an toàn
                w_ctx = (
                    f"Nhiệt độ {weather.get('temp','?')}°C, Độ ẩm {weather.get('hum','?')}%"
                    if isinstance(weather, dict)
                    else "Không có dữ liệu thời tiết thực địa"
                )

                # Prompt kỹ thuật chuyên sâu
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

                # Gọi AI
                response = model.generate_content(full_prompt)
                
                # Bảo vệ response (Phòng trường hợp AI chặn nội dung nhạy cảm)
                ai_res = response.text if hasattr(response, "text") else "⚠️ AI không thể trả lời câu hỏi này. Vui lòng hỏi về kỹ thuật nông nghiệp."

                # Hiển thị câu trả lời mới
                with st.chat_message("assistant"):
                    st.markdown(ai_res)

                # 3. LƯU VÀO DATABASE VÀ CẬP NHẬT GIAO DIỆN
                add_chat(data, prompt, ai_res)
                
                # Buộc Streamlit cập nhật lại để hiển thị lịch sử mới nhất
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Lỗi kết nối AI: {e}")
                st.info("Kiểm tra lại GEMINI_API_KEY trong file secrets của bạn.")                    
                    
