"""
weather.py - GREEN FARM
- get_weather               : thoi tiet hien tai
- get_forecast_7day         : du bao 7 ngay
- get_disease_pressure_48h  : ap luc benh 48h
- get_agri_warnings         : canh bao WMO code + gio
"""

import requests
from functools import lru_cache

_session = requests.Session()
_session.headers.update({"User-Agent": "GreenFarm/1.0 (greenfarm@example.com)"})

DEFAULT_LAT  = 16.4637
DEFAULT_LON  = 107.5909
DEFAULT_CITY = "Kim Long, Hue (Mac dinh)"

WEATHER_MAP = {
    0:  "Troi quang, nang rao",  1:  "Phan lon quang dang",
    2:  "May rai rac",           3:  "Troi nhieu may",
    45: "Suong mu",              48: "Suong mu dong bang",
    51: "Mua phun nhe",         53: "Mua phun vua",
    55: "Mua phun day",         61: "Mua nhe",
    63: "Mua vua",              65: "Mua nang hat",
    71: "Tuyet roi nhe",        80: "Mua rao nhe",
    81: "Mua rao vua",          82: "Mua rao manh",
    95: "Dong set",             96: "Dong kem mua da",
    99: "Dong manh kem mua da",
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
            "Vi tri cua ban"
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
        return ["Dang cho du lieu cam bien..."]

    warnings = []
    wind = wind or 0.0

    if hum > 85:
        if temp < 24:
            warnings.append(
                "⚠️ Nam Suong mai: Do am cao & troi mat, "
                "benh lay lan cuc nhanh. Phun Bordeaux hoac Trichoderma ngay."
            )
        else:
            warnings.append(
                "⚠️ Thoi re / Phan trang: Do am cao lam nam sinh soi. "
                "Kiem tra thoat nuoc, rai voi xung quanh goc."
            )
    elif 70 <= hum <= 85 and temp > 28:
        warnings.append(
            "🔍 Theo doi Heo xanh vi khuan: "
            "Dieu kien oi nong am rat thuan loi cho Ralstonia solanacearum."
        )

    if code in _CODE_CLEAR and temp > 32:
        warnings.append(
            "🚫 Bo tri / Nhen do: Thoi tiet kho nong "
            "giup con trung chich hut sinh san manh. Kiem tra mat duoi la."
        )

    if (51 <= code <= 67) or (80 <= code <= 82):
        warnings.append(
            "🛡️ Mua co the rua troi phan bon & thuoc BVTV. "
            "Che chan luong rau, kiem tra thoat nuoc muong ranh."
        )

    if 95 <= code <= 99:
        warnings.append(
            "⛈️ Dong bao: Gio manh co the gay canh, do cay. "
            "Cam coc chong do va buoc than cay truoc khi dong den."
        )

    if code in _CODE_FOG:
        warnings.append(
            "🌫️ Suong mu giu am tren la lau, "
            "de gay dom la & benh nam. Theo doi sat buoi sang."
        )

    if wind >= _WIND_DANGER:
        warnings.append(
            f"💨 CANH BAO GIO MANH ({wind:.0f} km/h): Nguy co cao do nga cay. "
            "Cam coc giu chac, thu hoach rau mau sap lua neu co the."
        )
    elif wind >= _WIND_CAUTION:
        warnings.append(
            f"🌬️ Gio vua ({wind:.0f} km/h): Cay than thao (ot, ca chua, dua leo) "
            "co the bi nghieng. Kiem tra day buoc va coc chong."
        )

    return warnings if warnings else ["✅ Thoi tiet hien tai rat on dinh cho canh tac."]


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
                risk = "high"
            elif hum > 75 or (51 <= code <= 82):
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
                "desc":     WEATHER_MAP.get(code, "On dinh"),
                "risk":     risk,
            })
        return result

    except Exception as e:
        print(f"Loi du bao 7 ngay: {e}")
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

        score = min(int(score_total / (10 * 48) * 100), 100)
        warnings = []

        if score >= 60 or hours_risk >= 20:
            level = "critical"
            warnings.append("⛔ AP LUC BENH CUC CAO: Nam va vi khuan se bung phat trong 48h. Xu ly ngay!")
        elif score >= 40 or hours_risk >= 12:
            level = "high"
            warnings.append("🔴 Ap luc benh cao: Dieu kien rat thuan loi cho nam benh phat trien.")
        elif score >= 20 or hours_risk >= 6:
            level = "medium"
            warnings.append("🟡 Ap luc benh trung binh: Can theo doi chat va phun phong ngua.")
        else:
            level = "low"
            warnings.append("🟢 Ap luc benh thap: Dieu kien kha an toan trong 48h toi.")

        if hours_risk >= 6:
            warnings.append(
                f"⏰ Co {hours_risk} gio nguy hiem trong 48h, cao diem luc {peak_time}. "
                "Uu tien phun Trichoderma hoac Nano Bac truoc gio cao diem."
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
        print(f"Loi ap luc benh 48h: {e}")
        return {
            "level": "unknown", "score": 0, "hours_risk": 0,
            "peak_time": "", "warnings": ["Khong lay duoc du lieu du bao."],
            "hourly": [],
        }


def get_weather(lat=None, lon=None) -> dict:
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
        if lat is None or lon is None:
            raise ValueError("Thieu toa do")
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
            raise ValueError("Phan hoi API thieu truong 'current'")

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
            "desc": WEATHER_MAP.get(code, "On dinh"),
            "code": code,
            "lat":  lat,
            "lon":  lon,
            "city": city,
            "agri_warnings": get_agri_warnings(temp, hum, code, wind),
        }

    except requests.exceptions.Timeout:
        print(f"Timeout ({lat}, {lon})")
    except requests.exceptions.ConnectionError:
        print("Khong co ket noi mang")
    except requests.exceptions.HTTPError as e:
        print(f"Loi HTTP: {e}")
    except (ValueError, KeyError) as e:
        print(f"Du lieu khong hop le: {e}")
    except Exception as e:
        print(f"Loi khong xac dinh: {e}")

    return {
        "temp": None, "hum": None, "wind": None, "rain": None,
        "desc": "Du lieu du phong (offline)",
        "code": -1, "lat": lat, "lon": lon, "city": city,
        "agri_warnings": ["⚠️ Khong lay duoc du lieu thoi tiet. Kiem tra ket noi mang."],
    }
