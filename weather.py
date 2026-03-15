import requests
from config import WEATHER_API, WEATHER_KEY


def get_weather(lat, lon):

    try:

        url = f"{WEATHER_API}?lat={lat}&lon={lon}&appid={WEATHER_KEY}&units=metric"

        r = requests.get(url).json()

        return {
            "temp": r["main"]["temp"],
            "hum": r["main"]["humidity"],
            "wind": r["wind"]["speed"]
        }

    except:

        return {
            "temp": 30,
            "hum": 70,
            "wind": 2
        }

