import requests

def get_agri_warnings(temp, hum, desc):
    if temp is None or hum is None:
        return ["Đang chờ dữ liệu cảm biến để đưa ra cảnh báo..."]

    warnings = []

    if hum > 85:
        if temp < 24:
            warnings.append("⚠️ Cảnh báo Nấm Sương mai: Độ ẩm cao & trời mát, bệnh lây lan cực nhanh.")
        else:
            warnings.append("⚠️ Cảnh báo Thối rễ/Phấn trắng: Độ ẩm cao làm nấm sinh sôi, cần kiểm tra thoát nước.")
    elif 70 <= hum <= 85 and temp > 28:
        warnings.append("🔍 Theo dõi bệnh Héo xanh: Vi khuẩn phát triển mạnh trong điều kiện oi nóng, ẩm.")

    desc_low = desc.lower()
    if any(word in desc_low for word in ["nắng", "quang", "ít mây"]):
        if temp > 32:
            warnings.append("🚫 Cảnh báo Bọ trĩ/Nhện đỏ: Thời tiết khô nóng giúp côn trùng chích hút sinh sản mạnh.")

    if "mưa" in desc_low or "dông" in desc_low:
        warnings.append("🛡️ Lưu ý: Mưa gây rửa trôi phân bón/thuốc BVTV, hãy che chắn cho rau màu.")
    if "sương mù" in desc_low:
        warnings.append("🌫️ Lưu ý: Sương mù tăng độ ẩm lá, dễ gây đốm lá, cần theo dõi sát.")

    return warnings if warnings else ["✅ Thời tiết hiện tại rất ổn định cho canh tác."]


def get_weather(lat=None, lon=None):
    DEFAULT_LAT, DEFAULT_LON = 16.4637, 107.5909
    DEFAULT_CITY = "Huế (Mặc định)"

    if lat is not None and lon is not None:
        try:
            lat  = float(lat)
            lon  = float(lon)
            city = "Vị trí của bạn"
        except (ValueError, TypeError):
            lat, lon = DEFAULT_LAT, DEFAULT_LON
            city = DEFAULT_CITY
    else:
        lat, lon = DEFAULT_LAT, DEFAULT_LON
        city = DEFAULT_CITY

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code"
            f"&timezone=auto"
        )
        response = requests.get(url, timeout=8)
        data     = response.json()

        if response.status_code == 200 and "current" in data:
            curr = data["current"]

            weather_map = {
                0:  "Trời quang, nắng ráo",    1:  "Phần lớn quang đãng",
                2:  "Mây rải rác",              3:  "Trời nhiều mây",
                45: "Sương mù",                 48: "Sương mù đóng băng",
                51: "Mưa phùn nhẹ",             53: "Mưa phùn vừa",
                55: "Mưa phùn dày",             61: "Mưa nhẹ",
                63: "Mưa vừa",                  65: "Mưa nặng hạt",
                71: "Tuyết rơi nhẹ",            80: "Mưa rào nhẹ",
                81: "Mưa rào vừa",              82: "Mưa rào mạnh",
                95: "Dông sét",                 96: "Dông kèm mưa đá",
                99: "Dông mạnh kèm mưa đá"
            }

            code = curr.get("weather_code", 0)
            desc = weather_map.get(code, "Thời tiết ổn định")
            temp = curr.get("temperature_2m")
            hum  = curr.get("relative_humidity_2m")

            return {
                "temp": temp,
                "hum":  hum,
                "wind": round(curr.get("wind_speed_10m") or 0, 1),
                "rain": curr.get("precipitation") or 0,
                "desc": desc,
                "lat":  lat,
                "lon":  lon,
                "city": city,
                "agri_warnings": get_agri_warnings(temp, hum, desc)
            }

    except Exception as e:
        print(f"❌ Lỗi API thời tiết: {e}")

    return {
        "temp": 27.0,
        "hum":  75,
        "wind": 1.2,
        "rain": 0,
        "desc": "Dữ liệu dự phòng (offline)",
        "lat":  lat,
        "lon":  lon,
        "city": city,
        "agri_warnings": ["⚠️ Đang chạy chế độ offline, vui lòng kiểm tra kết nối."]
    }
