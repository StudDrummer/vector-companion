"""Weather for the briefing and "what's the weather", from Open-Meteo (free, no key, no account)."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from . import settings as S

STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
          "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
          "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
          "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
          "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
          "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
          "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}

CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
         51: "drizzly", 53: "drizzly", 55: "drizzly", 56: "freezing drizzle", 57: "freezing drizzle",
         61: "light rain", 63: "rainy", 65: "pouring", 66: "freezing rain", 67: "freezing rain",
         71: "light snow", 73: "snowy", 75: "heavy snow", 77: "snow grains", 80: "showery", 81: "showery",
         82: "stormy showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
         96: "thunderstorms with hail", 99: "thunderstorms with hail"}

_cache: dict = {}


def _get(url: str, timeout: float = 6) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def locate(place: str) -> tuple[float, float, str]:
    if place in _cache.get("geo", {}):
        return _cache["geo"][place]
    city, _, region = (x.strip() for x in place.partition(","))
    res = _get("https://geocoding-api.open-meteo.com/v1/search?" +
               urllib.parse.urlencode({"name": city, "count": 10, "language": "en"})).get("results") or []
    if not res:
        raise RuntimeError(f"couldn't find {place}")
    want = STATES.get(region.upper(), region).lower()
    pick = next((r for r in res if want and want in (str(r.get("admin1", "")) + " " + str(r.get("country", ""))).lower()),
                res[0])
    out = (pick["latitude"], pick["longitude"], pick["name"])
    _cache.setdefault("geo", {})[place] = out
    return out


def forecast() -> dict:
    cfg = S.load()["weather"]
    key = (cfg["place"], cfg["units"])
    hit = _cache.get("fc")
    if hit and hit[0] == key and time.time() - hit[1] < 1200:
        return hit[2]
    lat, lon, name = locate(cfg["place"])
    q = {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
         "current": "temperature_2m,weather_code,apparent_temperature",
         "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
         "temperature_unit": "celsius" if cfg["units"] == "celsius" else "fahrenheit"}
    d = _get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))
    d["place"] = name
    _cache["fc"] = (key, time.time(), d)
    return d


def sentence(day: str = "today") -> str:
    """One or two spoken sentences, e.g. for the morning briefing."""
    d = forecast()
    i = 1 if day == "tomorrow" else 0
    dl = d["daily"]
    hi, lo = round(dl["temperature_2m_max"][i]), round(dl["temperature_2m_min"][i])
    rain = dl.get("precipitation_probability_max", [None, None])[i]
    sky = CODES.get(dl["weather_code"][i], "mixed")
    if i == 0:
        cur = d["current"]
        now_sky = CODES.get(cur["weather_code"], sky)
        out = f"It's {round(cur['temperature_2m'])} degrees and {now_sky} in {d['place']}, with a high of {hi} and a low of {lo}."
    else:
        out = f"Tomorrow in {d['place']}: {sky}, high of {hi}, low of {lo}."
    if rain is not None and rain >= 40:
        out += f" {rain} percent chance of rain, so take a jacket."
    elif lo <= (0 if S.load()["weather"]["units"] == "celsius" else 35):
        out += " It'll be cold, so bundle up."
    return out
