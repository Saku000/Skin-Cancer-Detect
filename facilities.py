"""
facilities.py — Deterministic nearby facility lookup via OpenStreetMap Overpass API.

Unlike AI web search, Overpass returns fixed OSM data sorted by real distance,
so the same location always produces the same ranked list.
"""

import json
import math
import urllib.parse
import urllib.request

OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS      = {"User-Agent": "SkinCancerDetect/1.0 (research tool)"}

# OSM amenity tags to search for
_AMENITY_FILTER = "hospital|clinic|doctors"


# ── Geo helpers ────────────────────────────────────────────────────────────────

def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _http_get(url: str, params: dict = None) -> dict | None:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[facilities] GET {url[:60]}… failed: {e}")
        return None


def _http_post(url: str, data: str) -> dict | None:
    body = data.encode()
    req  = urllib.request.Request(url, data=body, headers={
        **_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[facilities] POST {url[:60]}… failed: {e}")
        return None


# ── Geocoding ──────────────────────────────────────────────────────────────────

def _nominatim(q: str, country: str = "us") -> tuple[float, float] | None:
    params = {"format": "json", "limit": 1, "q": q}
    if country:
        params["countrycodes"] = country
    data = _http_get(NOMINATIM_URL, params)
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])
    return None


def geocode(query: str) -> tuple[float, float] | None:
    """
    Return (lat, lon) for a free-text address query.
    Falls back progressively: full address → city+state → city only.
    """
    # 1. Full query (US)
    pos = _nominatim(query, "us")
    if pos:
        return pos

    # 2. Full query (no country filter)
    pos = _nominatim(query, "")
    if pos:
        return pos

    # 3. City, state — last two comma parts (e.g. "Irvine, CA")
    parts = [p.strip() for p in query.split(",") if p.strip()]
    if len(parts) >= 2:
        city_state = ", ".join(parts[-2:])
        pos = _nominatim(city_state, "us")
        if pos:
            print(f"[facilities] geocode fell back to city/state: {city_state!r}")
            return pos

    # 4. Last part only (city or state)
    if parts:
        pos = _nominatim(parts[-1], "us")
        if pos:
            return pos

    return None


# ── Overpass query ─────────────────────────────────────────────────────────────

def _overpass_query(lat: float, lon: float, radius_m: int) -> list[dict]:
    # Cover both amenity=* and healthcare=* tagging schemes used in US OSM data
    amenity    = "hospital|clinic|doctors"
    healthcare = "hospital|clinic|doctor|centre|center"
    r          = radius_m

    query = (
        f"[out:json][timeout:30];\n"
        f"(\n"
        f'  node["amenity"~"{amenity}"]["name"](around:{r},{lat},{lon});\n'
        f'  way["amenity"~"{amenity}"]["name"](around:{r},{lat},{lon});\n'
        f'  relation["amenity"~"{amenity}"]["name"](around:{r},{lat},{lon});\n'
        f'  node["healthcare"~"{healthcare}"]["name"](around:{r},{lat},{lon});\n'
        f'  way["healthcare"~"{healthcare}"]["name"](around:{r},{lat},{lon});\n'
        f'  relation["healthcare"~"{healthcare}"]["name"](around:{r},{lat},{lon});\n'
        f");\n"
        f"out center tags;"
    )
    payload = urllib.parse.urlencode({"data": query})
    data    = _http_post(OVERPASS_URL, payload)
    return data.get("elements", []) if data else []


def _parse_element(el: dict, user_lat: float, user_lon: float) -> dict | None:
    tags = el.get("tags", {})
    name = tags.get("name", "").strip()
    if not name:
        return None

    # Coordinates
    if el["type"] == "node":
        elat, elon = float(el["lat"]), float(el["lon"])
    else:
        c = el.get("center", {})
        if not c:
            return None
        elat, elon = float(c["lat"]), float(c["lon"])

    # Build address from OSM tags
    parts = []
    hn = tags.get("addr:housenumber", "")
    st = tags.get("addr:street", "")
    if hn and st:
        parts.append(f"{hn} {st}")
    elif st:
        parts.append(st)
    city  = tags.get("addr:city", "")
    state = tags.get("addr:state", "")
    pc    = tags.get("addr:postcode", "")
    if city:
        parts.append(city)
    if state and pc:
        parts.append(f"{state} {pc}")
    elif state:
        parts.append(state)

    phone = (tags.get("phone") or tags.get("contact:phone") or
             tags.get("contact:mobile") or "").strip()

    return {
        "name":        name,
        "address":     ", ".join(parts),
        "phone":       phone,
        "distance_mi": round(_haversine_mi(user_lat, user_lon, elat, elon), 2),
        "lat":         elat,
        "lon":         elon,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def find_nearby(
    location: str,
    n: int = 4,
    radius_m: int = 25_000,
) -> tuple[list[dict], tuple[float, float] | None]:
    """
    Geocode `location` and return (facilities, (lat, lon)).
    Facilities are sorted by distance, deduplicated by name.
    Prefers results that have a street address; falls back to address-less ones
    only when needed to fill n slots.
    Falls back to a larger radius if fewer than n results found.
    Returns ([], None) on failure.
    """
    coords = geocode(location)
    if not coords:
        print(f"[facilities] geocode failed for: {location!r}")
        return [], None

    lat, lon = coords
    # Fetch extra candidates so we can prefer ones with addresses
    fetch_n  = n * 3
    elements = _overpass_query(lat, lon, radius_m)

    # Widen search if sparse results
    if len(elements) < fetch_n:
        elements = _overpass_query(lat, lon, radius_m * 2)

    parsed = []
    seen   = set()
    for el in elements:
        f = _parse_element(el, lat, lon)
        if f and f["name"] not in seen:
            seen.add(f["name"])
            parsed.append(f)

    parsed.sort(key=lambda x: x["distance_mi"])

    # Prefer facilities that have an address; fill remaining slots from the rest
    with_addr    = [f for f in parsed if f.get("address")]
    without_addr = [f for f in parsed if not f.get("address")]
    ordered = with_addr[:n]
    if len(ordered) < n:
        ordered += without_addr[: n - len(ordered)]

    # Re-sort by distance after prioritisation
    ordered.sort(key=lambda x: x["distance_mi"])
    return ordered[:n], coords
