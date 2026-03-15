import requests

def get_agri_warnings(temp, hum, desc):
    """
    Logic cảnh báo chuyên sâu cho nông nghiệp.
    Kiểm tra dữ liệu hợp lệ trước khi phân tích.
    """
    if temp is None or hum is None:
        return ["Đang chờ dữ liệu cảm biến để đưa ra cảnh báo..."]
        
    warnings = []
    
    # 1. Cảnh báo Nấm bệnh
    if hum > 85:
        if temp < 24:
            warnings.append("⚠️ Cảnh báo Nấm Sương mai: Độ ẩm cao & trời mát, bệnh lây lan cực nhanh.")
        else:
            warnings.append("⚠️ Cảnh báo Thối rễ/Phấn trắng: Độ ẩm cao làm nấm sinh sôi, cần kiểm tra thoát nước.")
    elif 70 <= hum <= 85 and temp > 28:
        warnings.append("🔍 Theo dõi bệnh Héo xanh: Vi khuẩn phát triển mạnh trong điều kiện oi nóng, ẩm.")

    # 2. Cảnh báo Côn trùng
    desc_low = desc.lower()
    if any(word in desc_low for word in ["nắng", "quang", "ít mây"]):
        if temp > 32:
            warnings.append("🚫 Cảnh báo Bọ trĩ/Nhện đỏ: Thời tiết khô nóng giúp côn trùng chích hút sinh sản mạnh.")
    
    # 3. Cảnh báo theo thời tiết cực đoan
    if "mưa" in desc_low or "dông" in desc_low:
        warnings.append("🛡️ Lưu ý: Mưa gây rửa trôi phân bón/thuốc BVTV, hãy che chắn cho rau màu.")
    if "sương mù" in desc_low:
        warnings.append("🌫️ Lưu ý: Sương mù tăng độ ẩm lá, dễ gây đốm lá, cần theo dõi sát.")

    return warnings if warnings else ["✅ Thời tiết hiện tại rất ổn định cho canh tác."]

def get_weather(lat=None, lon=None):
    """
    Hàm lấy thời tiết toàn diện với cơ chế dự phòng an toàn.
    """
    # Mặc định tọa độ Huế để tránh biến None
    default_lat, default_lon = 16.4637, 107.5909
    city = "Huế (Mặc định)"

    # BƯỚC 1: XÁC ĐỊNH VỊ TRÍ & FALLBACK
    if lat is None or lon is None:
        try:
            geo_res = requests.get("https://ipapi.co/json/", timeout=3)
            geo_data = geo_res.json()
            # Nếu API trả về None hoặc lỗi, dùng giá trị mặc định
            lat = geo_data.get("latitude") or default_lat
            lon = geo_data.get("longitude") or default_lon
            city = geo_data.get("city") or "Vị trí của bạn"
            print(f"📍 Định vị: {city} ({lat}, {lon})")
        except:
            lat, lon = default_lat, default_lon
            city = "Huế (Dự phòng)"
            print("⚠️ Lỗi định vị → dùng Fallback")
    
    # BƯỚC 2: GỌI API THỜI TIẾT
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code"
            f"&timezone=auto"
        )
        response = requests.get(url, timeout=5)
        data = response.json()

        if response.status_code == 200 and "current" in data:
            curr = data["current"]
            
            # Weather Map đầy đủ hơn (Dựa trên bảng mã WMO)
            weather_map = {
                0: "Trời quang, nắng ráo", 1: "Phần lớn quang đãng", 2: "Mây rải rác", 3: "Trời nhiều mây",
                45: "Sương mù", 48: "Sương mù đóng băng", 51: "Mưa phùn nhẹ", 53: "Mưa phùn vừa",
                55: "Mưa phùn dày", 61: "Mưa nhẹ", 63: "Mưa vừa", 65: "Mưa nặng hạt",
                71: "Tuyết rơi nhẹ", 80: "Mưa rào nhẹ", 81: "Mưa rào vừa", 82: "Mưa rào mạnh",
                95: "Dông sét", 96: "Dông kèm mưa đá", 99: "Dông mạnh kèm mưa đá"
            }
            
            code = curr.get("weather_code", 0)
            desc = weather_map.get(code, "Thời tiết ổn định")
            temp = curr.get("temperature_2m")
            hum = curr.get("relative_humidity_2m")

            return {
                "temp": temp,
                "hum": hum,
                "wind": round(curr.get("wind_speed_10m") or 0, 1),
                "rain": curr.get("precipitation") or 0,
                "desc": desc,
                "lat": lat,
                "lon": lon,
                "city": city,
                "agri_warnings": get_agri_warnings(temp, hum, desc)
            }

    except Exception as e:
        print(f"❌ Lỗi API: {e}")

    # BƯỚC 3: TRẢ VỀ DỮ LIỆU OFFLINE AN TOÀN (Tuyệt đối không có None)
    return {
        "temp": 27.0,
        "hum": 75,
        "wind": 1.2,
        "rain": 0,
        "desc": "Dữ liệu dự phòng",
        "lat": lat or default_lat,
        "lon": lon or default_lon,
        "city": city,
        "agri_warnings": ["Đang chạy chế độ offline, vui lòng kiểm tra kết nối."]
    }
