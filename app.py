"""
weather.py - GREEN FARM
────────────────────────────────────────────────────────────
Module thời tiết hoàn chỉnh:
  - get_city_name    : reverse geocoding, cache lru_cache module-level
  - get_agri_warnings: dựa trên WMO code + cảnh báo tốc độ gió (km/h)
  - get_weather      : gọi Open-Meteo, trả dict chuẩn, không tự cache
                       (cache được xử lý ở tầng gọi bằng @st.cache_data)
"""

import requests
from functools import lru_cache

# ─────────────────────────────────────────────────────────────
# SESSION DÙNG CHUNG (keep-alive, tăng tốc)
# ─────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({"User-Agent": "GreenFarm/1.0 (greenfarm@example.com)"})

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

DEFAULT_LAT  = 16.4637
DEFAULT_LON  = 107.5909
DEFAULT_CITY = "Huế (Mặc định)"

WEATHER_MAP = {
    0:  "Trời quang, nắng ráo",  1:  "Phần lớn quang đãng",
    2:  "Mây rải rác",           3:  "Trời nhiều mây",
    45: "Sương mù",              48: "Sương mù đóng băng",
    51: "Mưa phùn nhẹ",         53: "Mưa phùn vừa",
    55: "Mưa phùn dày",         61: "Mưa nhẹ",
    63: "Mưa vừa",              65: "Mưa nặng hạt",
    71: "Tuyết rơi nhẹ",        80: "Mưa rào nhẹ",
    81: "Mưa rào vừa",          82: "Mưa rào mạnh",
    95: "Dông sét",             96: "Dông kèm mưa đá",
    99: "Dông mạnh kèm mưa đá",
}

# WMO code groups (set để O(1) lookup)
_CODE_CLEAR = {0, 1}
_CODE_FOG   = {45, 48}

# Ngưỡng gió cảnh báo — Open-Meteo mặc định đơn vị km/h
_WIND_CAUTION = 20   # cây thân thảo bắt đầu có nguy cơ nghiêng
_WIND_DANGER  = 40   # nguy cơ đổ ngã, gãy cành cao


# ─────────────────────────────────────────────────────────────
# REVERSE GEOCODING
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _geocode_cached(lat_r: float, lon_r: float) -> str:
    # Ưu tiên Nominatim
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat_r}&lon={lon_r}&format=json&accept-language=vi"
        )
        res = _session.get(url, timeout=5)
        res.raise_for_status()
        addr = res.json().get("address", {})
        city = (
            addr.get("city") or addr.get("town") or
            addr.get("village") or addr.get("county") or
            "Vị trí của bạn"
        )
        return city
    except requests.exceptions.RequestException:
        pass

    # Fallback: timezone từ Open-Meteo
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat_r}&longitude={lon_r}"
            f"&timezone=auto&forecast_days=0"
        )
        res = _session.get(url, timeout=5)
        res.raise_for_status()
        tz = res.json().get("timezone", "")
        if "/" in tz:
            return tz.split("/")[-1].replace("_", " ")
    except requests.exceptions.RequestException:
        pass

    return DEFAULT_CITY


def get_city_name(lat: float, lon: float) -> str:
    """Public wrapper — làm tròn tọa độ trước khi vào cache."""
    return _geocode_cached(round(lat, 2), round(lon, 2))


# ─────────────────────────────────────────────────────────────
# CẢNH BÁO NÔNG NGHIỆP
# ─────────────────────────────────────────────────────────────

def get_agri_warnings(
    temp,
    hum,
    code: int,
    wind: float = 0.0,
) -> list:
    if temp is None or hum is None:
        return ["⏳ Đang chờ dữ liệu cảm biến để đưa ra cảnh báo..."]

    warnings = []
    wind = wind or 0.0

    # ── 1. Nấm bệnh theo độ ẩm & nhiệt độ ───────────────────
    if hum > 85:
        if temp < 24:
            warnings.append(
                "⚠️ Cảnh báo Nấm Sương mai: Độ ẩm cao & trời mát, "
                "bệnh lây lan cực nhanh. Phun Bordeaux hoặc Trichoderma ngay."
            )
        else:
            warnings.append(
                "⚠️ Cảnh báo Thối rễ / Phấn trắng: Độ ẩm cao làm nấm sinh sôi. "
                "Kiểm tra thoát nước, rải vôi xung quanh gốc."
            )
    elif 70 <= hum <= 85 and temp > 28:
        warnings.append(
            "🔍 Theo dõi bệnh Héo xanh vi khuẩn: "
            "Điều kiện oi nóng ẩm rất thuận lợi cho Ralstonia solanacearum."
        )

    # ── 2. Côn trùng — nắng khô nóng ─────────────────────────
    if code in _CODE_CLEAR and temp > 32:
        warnings.append(
            "🚫 Cảnh báo Bọ trĩ / Nhện đỏ: Thời tiết khô nóng "
            "giúp côn trùng chích hút sinh sản mạnh. Kiểm tra mặt dưới lá."
        )

    # ── 3. Mưa (WMO 51-67 và 80-82) ──────────────────────────
    if (51 <= code <= 67) or (80 <= code <= 82):
        warnings.append(
            "🛡️ Lưu ý: Mưa có thể rửa trôi phân bón & thuốc BVTV. "
            "Che chắn luống rau, kiểm tra thoát nước mương rãnh."
        )

    # ── 4. Dông bão (WMO 95-99) ──────────────────────────────
    if 95 <= code <= 99:
        warnings.append(
            "⛈️ Cảnh báo Dông bão: Gió mạnh có thể gãy cành, đổ cây. "
            "Cắm cọc chống đỡ và buộc thân cây trước khi dông đến."
        )

    # ── 5. Sương mù ───────────────────────────────────────────
    if code in _CODE_FOG:
        warnings.append(
            "🌫️ Lưu ý: Sương mù giữ ẩm trên lá lâu, "
            "dễ gây đốm lá & bệnh nấm. Theo dõi sát buổi sáng."
        )

    # ── 6. Tốc độ gió (km/h) ─────────────────────────────────
    if wind >= _WIND_DANGER:
        warnings.append(
            f"💨 CẢNH BÁO GIÓ MẠNH ({wind:.0f} km/h): Nguy cơ cao đổ ngã cây, "
            "gãy cành. Cắm cọc giữ chắc, thu hoạch rau màu sắp lứa nếu có thể."
        )
    elif wind >= _WIND_CAUTION:
        warnings.append(
            f"🌬️ Gió vừa ({wind:.0f} km/h): Cây thân thảo (ớt, cà chua, dưa leo) "
            "có thể bị nghiêng. Kiểm tra dây buộc và cọc chống."
        )

    return warnings if warnings else ["✅ Thời tiết hiện tại rất ổn định cho canh tác."]


# ─────────────────────────────────────────────────────────────
# HÀM CHÍNH
# ─────────────────────────────────────────────────────────────

def get_weather(lat=None, lon=None) -> dict:
    # Validate tọa độ
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
        if lat is None or lon is None:
            raise ValueError("Thiếu tọa độ")
    except (ValueError, TypeError):
        lat, lon = DEFAULT_LAT, DEFAULT_LON

    city = get_city_name(lat, lon)

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,"
            f"wind_speed_10m,precipitation,weather_code"
            f"&timezone=auto"
        )
        res = _session.get(url, timeout=8)
        res.raise_for_status()

        data = res.json()
        if "current" not in data:
            raise ValueError("Phản hồi API thiếu trường 'current'")

        curr = data["current"]
        code = curr.get("weather_code", 0)
        temp = curr.get("temperature_2m")
        hum  = curr.get("relative_humidity_2m")
        wind = round(curr.get("wind_speed_10m") or 0.0, 1)  # km/h

        return {
            "temp": temp,
            "hum":  hum,
            "wind": wind,
            "rain": curr.get("precipitation") or 0,
            "desc": WEATHER_MAP.get(code, "Thời tiết ổn định"),
            "code": code,
            "lat":  lat,
            "lon":  lon,
            "city": city,
            "agri_warnings": get_agri_warnings(temp, hum, code, wind),
        }

    except requests.exceptions.Timeout:
        print(f"⏱️ Timeout khi gọi Open-Meteo ({lat}, {lon})")
    except requests.exceptions.ConnectionError:
        print("🔌 Không có kết nối mạng")
    except requests.exceptions.HTTPError as e:
        print(f"🌐 Lỗi HTTP từ Open-Meteo: {e}")
    except (ValueError, KeyError) as e:
        print(f"📦 Dữ liệu API không hợp lệ: {e}")
    except Exception as e:
        print(f"❌ Lỗi không xác định: {e}")

    return {
        "temp": None,
        "hum":  None,
        "wind": None,
        "rain": None,
        "desc": "Dữ liệu dự phòng (offline)",
        "code": -1,
        "lat":  lat,
        "lon":  lon,
        "city": city,
        "agri_warnings": [
            "⚠️ Không lấy được dữ liệu thời tiết. Kiểm tra kết nối mạng."
        ],
    }
