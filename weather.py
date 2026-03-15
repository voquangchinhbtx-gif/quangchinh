import requests
from config import WEATHER_API, WEATHER_KEY


def get_weather(lat, lon):
    """
    Lấy dữ liệu thời tiết từ OpenWeatherMap theo tọa độ GPS.

    Thông tin trả về gồm:
    - temp : nhiệt độ (°C)
    - hum  : độ ẩm (%)
    - wind : tốc độ gió (m/s)
    - rain : lượng mưa 1 giờ gần nhất (mm)
    - desc : mô tả thời tiết (tiếng Việt)

    Nếu API lỗi hoặc mất mạng, hàm sẽ trả về dữ liệu ngoại tuyến
    để ứng dụng không bị crash.
    """

    try:

        url = (
            f"{WEATHER_API}"
            f"?lat={lat}"
            f"&lon={lon}"
            f"&appid={WEATHER_KEY}"
            f"&units=metric"
            f"&lang=vi"
        )

        response = requests.get(url, timeout=5)

        data = response.json()

        # Kiểm tra API trả dữ liệu hợp lệ
        if response.status_code != 200 or "main" not in data:

            print("Lỗi API thời tiết:", data.get("message"))

            return None

        # Trả dữ liệu cần thiết cho app
        weather = {

            "temp": data["main"]["temp"],

            "hum": data["main"]["humidity"],

            "wind": data["wind"]["speed"],

            "rain": data.get("rain", {}).get("1h", 0),

            "desc": data["weather"][0]["description"]

        }

        return weather

    except requests.exceptions.Timeout:

        print("Lỗi: timeout khi kết nối OpenWeather")

    except requests.exceptions.ConnectionError:

        print("Lỗi: không có kết nối internet")

    except Exception as e:

        print("Lỗi không xác định:", e)

    # fallback dữ liệu ngoại tuyến để app vẫn chạy
    return {

        "temp": 28,

        "hum": 75,

        "wind": 1,

        "rain": 0,

        "desc": "dữ liệu ngoại tuyến"

    }
