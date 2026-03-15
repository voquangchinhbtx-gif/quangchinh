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

elif menu == "🌱 Quản lý Cây trồng":
    st.title("🌱 Quản lý Vườn & Quy trình AI Chuyên sâu")

    # ==========================================
    # 1. KHUNG QUẢN TRỊ (THÊM & SỬA)
    # ==========================================
    with st.expander("⚙️ Thiết lập danh sách cây trồng (Thêm/Sửa)"):
        tab_add, tab_edit = st.tabs(["➕ Thêm cây & Lập quy trình AI", "✏️ Chỉnh sửa thông tin"])
        
        with tab_add:
            c1, c2 = st.columns(2)
            with c1: 
                name_in = st.text_input("Tên định danh cây", placeholder="Ví dụ: Chậu ớt 01")
            with c2: 
                type_in = st.text_input("Loại cây (AI lập quy trình)", placeholder="Ví dụ: Ớt Aji Charapita")
            
            date_in = st.date_input("Ngày trồng thực tế", value=datetime.now())
            
            # --- XỬ LÝ NÚT AI CÓ SESSION STATE ĐỂ TRÁNH CHẠY LẠI KHI LOAD ---
            if st.button("🚀 AI Lập quy trình & Lưu vào vườn", key="btn_add_ai"):
                if name_in.strip() and type_in.strip():
                    with st.spinner(f"AI đang tra cứu dữ liệu mở cho {type_in}..."):
                        try:
                            # Cấu hình AI
                            model = genai.GenerativeModel("gemini-1.5-flash")
                            prompt = f"""
                            Lập quy trình chăm sóc chi tiết cho cây: {type_in}. 
                            Yêu cầu:
                            - Chia giai đoạn: Cây con, Sinh trưởng, Ra hoa/Trái. 
                            - Mỗi giai đoạn nêu cách tưới nước, bón phân hữu cơ và ngừa bệnh.
                            - Ngôn ngữ: Tiếng Việt, ngắn gọn, thực dụng.
                            """
                            res = model.generate_content(prompt)
                            
                            # 1️⃣ BẢO VỆ res.text - getattr chặn crash nếu res rỗng
                            result_text = getattr(res, "text", None) or "⚠️ AI chưa trả về văn bản quy trình."
                            
                            # Lưu vào Session State để hiển thị ngay mà không bị mất khi load lại
                            st.session_state[f"last_ai_plan"] = result_text
                            
                            # Lưu vào database
                            full_identity = f"{name_in} | {type_in}"
                            data = add_plant(data, full_identity, date_in.strftime("%Y-%m-%d"))
                            
                            st.success(f"Đã lưu thành công cây {name_in}!")
                        except Exception as e:
                            st.error(f"Lỗi hệ thống AI: {e}")
                else:
                    st.warning("Vui lòng không để trống Tên định danh hoặc Loại cây.")

            # Hiển thị quy trình AI vừa tạo (Nếu có trong ngăn nhớ tạm)
            if "last_ai_plan" in st.session_state:
                st.markdown("---")
                st.markdown("### 📋 Quy trình AI vừa lập:")
                st.info(st.session_state["last_ai_plan"])
                if st.button("🗑️ Đóng bảng quy trình"):
                    del st.session_state["last_ai_plan"]
                    st.rerun()

        with tab_edit:
            all_p = data.get("plants", [])
            if all_p:
                p_edit = st.selectbox("Chọn cây muốn chỉnh sửa", all_p, format_func=lambda x: x['name'])
                new_n = st.text_input("Đổi tên định danh", value=p_edit['name'])
                new_d = st.date_input("Sửa ngày trồng", value=datetime.strptime(p_edit['date'], "%Y-%m-%d"))
                
                if st.button("💾 Lưu cập nhật"):
                    for p in data['plants']:
                        if p['id'] == p_edit['id']:
                            p['name'], p['date'] = new_n, new_d.strftime("%Y-%m-%d")
                    st.success("Đã cập nhật thông tin!"); st.rerun()
            else:
                st.info("Chưa có cây nào để chỉnh sửa.")

    # ==========================================
    # 2. HIỂN THỊ DANH SÁCH & QUY TRÌNH (BẢO VỆ TUYỆT ĐỐI)
    # ==========================================
    plants_list = data.get("plants", [])
    
    if not plants_list:
        st.info("🌵 Vườn hiện tại chưa có cây. Hãy thêm cây mới ở trên.")
    else:
        for p in plants_list:
            with st.container(border=True):
                col_info, col_care, col_action = st.columns([1, 2, 1])
                
                # --- CỘT 1: THÔNG TIN (TÍNH TUỔI CHUẨN) ---
                with col_info:
                    st.subheader(f"🌿 {p['name']}")
                    # 5️⃣ TỐI ƯU TÍNH TUỔI CÂY (Theo Tèo - Chống ngày âm)
                    plant_date = datetime.strptime(p["date"], "%Y-%m-%d")
                    delta = datetime.now() - plant_date
                    age = max(delta.days, 0)
                    
                    st.write(f"⏱️ Tuổi cây: **{age} ngày**")
                    st.caption(f"📅 Trồng ngày: {p['date']}")

                # --- CỘT 2: PHÁC ĐỒ CHĂM SÓC (TỰ ĐỘNG THEO LOẠI) ---
                with col_care:
                    # 2️⃣ SỬA CÁCH TÁCH LOẠI CÂY (An toàn tuyệt đối)
                    parts = p["name"].split("|")
                    crop_type_extracted = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    
                    st.markdown(f"📋 **Quy trình: {crop_type_extracted}**")
                    
                    with st.expander("Phác đồ chi tiết từng giai đoạn"):
                        # 3️⃣ TRÁNH CRASH NẾU THIẾU KEY (Fallback về 'Chung')
                        k_key = next((k for k in CROP_KNOWLEDGE.keys() if k in p['name']), None)
                        stages = CROP_KNOWLEDGE.get(k_key, CROP_KNOWLEDGE.get("Chung", []))
                        
                        if stages:
                            # Tìm giai đoạn hiện tại
                            curr = next((s for s in stages if s['days'][0] <= age <= s['days'][1]), stages[-1])
                            
                            st.info(f"📍 Hiện tại: **{curr['stage']}**")
                            
                            t_org, t_back = st.tabs(["🍃 Hữu cơ", "🧪 Dự phòng"])
                            with t_org:
                                st.write(curr["organic"])
                                st.caption(f"Vật tư: {FARM_RESOURCES['Dinh dưỡng']['Hữu cơ (Ưu tiên)']}")
                            with t_back:
                                st.write(curr["backup"])
                            
                            st.caption(f"📌 **Ghi chú:** {curr['note']}")
                            
                            # 4️⃣ BẢO VỆ WEATHER KHI GỌI CẢNH BÁO
                            warn = ai_crop_warning(curr["stage"], weather) if weather else None
                            if warn:
                                st.error(f"🤖 AI Nhắc nhở: {warn}")
                        else:
                            st.warning("⚠️ Chưa có dữ liệu phác đồ sẵn có.")

                # --- CỘT 3: THAO TÁC (XÓA 2 LỚP - HỎI LÝ DO) ---
                with col_action:
                    st.caption("⚙️ Thao tác nhanh")
                    
                    with st.popover("🗑️ Gỡ bỏ cây"):
                        st.warning(f"Xác nhận gỡ {p['name']}?")
                        reason = st.radio(
                            "Lý do gỡ bỏ:", 
                            ["🎉 Đã thu hoạch", "🥀 Cây hỏng/Nhổ bỏ"], 
                            key=f"re_{p['id']}"
                        )
                        
                        if st.button("✔️ Chốt gỡ", key=f"del_{p['id']}", type="primary"):
                            data = delete_plant(data, p["id"])
                            if "thu hoạch" in reason.lower():
                                st.toast(f"Đã lưu thu hoạch {p['name']}!", icon="🎊")
                            st.rerun()

                    # Tiện ích thời tiết mini bảo vệ bằng .get()
                    if weather and isinstance(weather, dict):
                        st.divider()
                        temp = weather.get('temp', 0)
                        hum = weather.get('hum', 0)
                        if temp > 32: st.warning(f"🥵 {temp}°C (Nóng)")
                        if hum > 80: st.error(f"🦠 {hum}% (Ẩm)")


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
                    
