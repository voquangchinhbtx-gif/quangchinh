# -*- coding: utf-8 -*-
"""
weather.py - GREEN FARM
"""

import requests
from functools import lru_cache

_session = requests.Session()
_session.headers.update({"User-Agent": "GreenFarm/1.0 (greenfarm@example.com)"})

DEFAULT_LAT  = 16.4637
DEFAULT_LON  = 107.5909
DEFAULT_CITY = "Kim Long, Huế (Mặc định)"

WEATHER_MAP = {
    -1: "Dữ liệu ngoại tuyến",
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

_CODE_CLEAR   = {0, 1}
_CODE_FOG     = {45, 48}
_WIND_CAUTION = 20
_WIND_DANGER  = 40


@lru_cache(maxsize=256)
def _geocode_cached(lat_r: float, lon_r: float) -> str:
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat_r}&lon={lon_r}&format=json&accept-language=vi"
        )
        res = _session.get(url, timeout=5)
        res.raise_for_status()
        addr = res.json().get("address", {})
        return (
            addr.get("city") or addr.get("town") or
            addr.get("village") or addr.get("county") or
            "Vị trí của bạn"
        )
    except requests.exceptions.RequestException:
        pass
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat_r}&longitude={lon_r}&timezone=auto&forecast_days=0"
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
    return _geocode_cached(round(lat, 2), round(lon, 2))


def get_agri_warnings(temp, hum, code: int, wind: float = 0.0) -> list:
    if temp is None or hum is None:
        return ["⏳ Đang chờ dữ liệu cảm biến..."]

    warnings = []
    wind = wind or 0.0

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

    if code in _CODE_CLEAR and temp > 32:
        warnings.append(
            "🚫 Cảnh báo Bọ trĩ / Nhện đỏ: Thời tiết khô nóng "
            "giúp côn trùng chích hút sinh sản mạnh. Kiểm tra mặt dưới lá."
        )

    if (51 <= code <= 67) or (80 <= code <= 82):
        warnings.append(
            "🛡️ Lưu ý: Mưa có thể rửa trôi phân bón & thuốc BVTV. "
            "Che chắn luống rau, kiểm tra thoát nước mương rãnh."
        )

    if 95 <= code <= 99:
        warnings.append(
            "⛈️ Cảnh báo Dông bão: Gió mạnh có thể gãy cành, đổ cây. "
            "Cắm cọc chống đỡ và buộc thân cây trước khi dông đến."
        )

    if code in _CODE_FOG:
        warnings.append(
            "🌫️ Lưu ý: Sương mù giữ ẩm trên lá lâu, "
            "dễ gây đốm lá & bệnh nấm. Theo dõi sát buổi sáng."
        )

    if wind >= _WIND_DANGER:
        warnings.append(
            f"💨 CẢNH BÁO GIÓ MẠNH ({wind:.0f} km/h): Nguy cơ cao đổ ngã cây. "
            "Cắm cọc giữ chắc, thu hoạch rau màu sắp lứa nếu có thể."
        )
    elif wind >= _WIND_CAUTION:
        warnings.append(
            f"🌬️ Gió vừa ({wind:.0f} km/h): Cây thân thảo có thể bị nghiêng. "
            "Kiểm tra dây buộc và cọc chống."
        )

    return warnings if warnings else ["✅ Thời tiết hiện tại rất ổn định cho canh tác."]


def get_forecast_7day(lat: float, lon: float) -> list:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,"
        f"relative_humidity_2m_max,precipitation_sum,weather_code"
        f"&timezone=auto&forecast_days=7"
    )
    try:
        res = _session.get(url, timeout=8)
        res.raise_for_status()
        daily = res.json().get("daily", {})

        dates   = daily.get("time", [])
        t_max   = daily.get("temperature_2m_max", [])
        t_min   = daily.get("temperature_2m_min", [])
        hum_max = daily.get("relative_humidity_2m_max", [])
        rain    = daily.get("precipitation_sum", [])
        codes   = daily.get("weather_code", [])

        result = []
        for i in range(len(dates)):
            hum  = hum_max[i] if i < len(hum_max) else 0
            tmp  = t_max[i]   if i < len(t_max)   else 0
            code = codes[i]   if i < len(codes)    else 0
            rn   = rain[i]    if i < len(rain)      else 0

            if hum > 85 and tmp < 26:
                risk = "critical"
            elif hum > 80 or (51 <= code <= 82):
                risk = "high"
            elif hum > 70 or code in (45, 48):
                risk = "medium"
            else:
                risk = "low"

            result.append({
                "date":     dates[i],
                "temp_max": tmp,
                "temp_min": t_min[i] if i < len(t_min) else 0,
                "hum_max":  hum,
                "rain":     rn,
                "code":     code,
                "desc":     WEATHER_MAP.get(code, "Ổn định"),
                "risk":     risk,
            })
        return result
    except Exception as e:
        print(f"Lỗi dự báo 7 ngày: {e}")
        return []


def get_disease_pressure_48h(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,weather_code"
        f"&timezone=auto&forecast_days=2"
    )
    try:
        res = _session.get(url, timeout=8)
        res.raise_for_status()
        hourly = res.json().get("hourly", {})

        times = hourly.get("time", [])[:48]
        temps = hourly.get("temperature_2m", [])[:48]
        hums  = hourly.get("relative_humidity_2m", [])[:48]
        codes = hourly.get("weather_code", [])[:48]

        hours_risk  = 0
        score_total = 0
        peak_score  = 0
        peak_time   = ""
        hourly_out  = []

        for i, (t, h, c) in enumerate(zip(temps, hums, codes)):
            s = 0
            if h is not None and h > 90:
                s += 4
            elif h is not None and h > 80:
                s += 2
            if t is not None and t < 24:
                s += 2
            if (51 <= c <= 67) or (80 <= c <= 82):
                s += 2
            if c in _CODE_FOG:
                s += 2

            score_total += s
            if s >= 5:
                hours_risk += 1
            if s > peak_score:
                peak_score = s
                peak_time  = times[i][11:16] if len(times[i]) >= 16 else times[i]

            risk_label = "high" if s >= 6 else "medium" if s >= 3 else "low"
            hourly_out.append({
                "time":  times[i][11:16] if len(times[i]) >= 16 else times[i],
                "temp":  t,
                "hum":   h,
                "risk":  risk_label,
                "score": s,
            })

        score    = min(int(score_total / (10 * 48) * 100), 100)
        warnings = []

        if score >= 60 or hours_risk >= 20:
            level = "critical"
            warnings.append("⛔ ÁP LỰC BỆNH CỰC CAO: Nấm và vi khuẩn sẽ bùng phát trong 48h. Xử lý ngay!")
        elif score >= 40 or hours_risk >= 12:
            level = "high"
            warnings.append("🔴 Áp lực bệnh cao: Điều kiện rất thuận lợi cho nấm bệnh phát triển.")
        elif score >= 20 or hours_risk >= 6:
            level = "medium"
            warnings.append("🟡 Áp lực bệnh trung bình: Cần theo dõi chặt và phun phòng ngừa.")
        else:
            level = "low"
            warnings.append("🟢 Áp lực bệnh thấp: Điều kiện khá an toàn trong 48h tới.")

        if hours_risk >= 6:
            warnings.append(
                f"⏰ Có {hours_risk} giờ nguy hiểm trong 48h, cao điểm lúc {peak_time}. "
                "Ưu tiên phun Trichoderma hoặc Nano Bạc trước giờ cao điểm."
            )

        return {
            "level":      level,
            "score":      score,
            "hours_risk": hours_risk,
            "peak_time":  peak_time,
            "warnings":   warnings,
            "hourly":     hourly_out,
        }

    except Exception as e:
        print(f"Lỗi áp lực bệnh 48h: {e}")
        return {
            "level": "unknown", "score": 0, "hours_risk": 0,
            "peak_time": "", "warnings": ["Không lấy được dữ liệu dự báo."],
            "hourly": [],
        }


def get_weather(lat=None, lon=None) -> dict:
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
        wind = round(curr.get("wind_speed_10m") or 0.0, 1)

        return {
            "temp": temp,
            "hum":  hum,
            "wind": wind,
            "rain": curr.get("precipitation") or 0,
            "desc": WEATHER_MAP.get(code, "Ổn định"),
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
        print(f"🌐 Lỗi HTTP: {e}")
    except (ValueError, KeyError) as e:
        print(f"📦 Dữ liệu không hợp lệ: {e}")
    except Exception as e:
        print(f"❌ Lỗi không xác định: {e}")

    return {
        "temp": None, "hum": None, "wind": None, "rain": None,
        "desc": "Dữ liệu dự phòng (offline)",
        "code": -1, "lat": lat, "lon": lon, "city": city,
        "agri_warnings": ["⚠️ Không lấy được dữ liệu thời tiết. Kiểm tra kết nối mạng."],
    }
