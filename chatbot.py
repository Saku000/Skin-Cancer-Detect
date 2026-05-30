"""
chatbot.py — AI assistant chat logic for skin lesion results

Endpoints consumed:
    POST /chat          -> chat_reply()  returns dict with reply + facilities
    POST /chat/summary  -> generate_summary()
"""

import os
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv
import facilities as _fac

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ── Config ────────────────────────────────────────────────────────────────────

MODEL       = "gemini-2.5-flash"
TEMPERATURE = 0

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are a warm, compassionate dermatology AI assistant with web search capability. "
    "Your primary role is to help users feel calm and supported when reviewing their skin analysis results. "
    "Many users may feel anxious or scared — always acknowledge their feelings first before giving information. "
    "Use a gentle, reassuring tone throughout. Remind them that an AI analysis is a screening tool, not a diagnosis, "
    "and that most skin conditions are very treatable when caught early. "
    "Encourage them to take the next step without causing alarm. "
    "Never make definitive medical diagnoses. "
    "When users ask for nearby clinics, dermatologists, or medical facilities, "
    "use your search capability to find options near their location. "
    "Search using specific distance-focused queries such as "
    "'dermatologist nearest to [address]' or 'skin clinic closest to [address]'. "
    "Always list results ordered by proximity — closest first. "
    "If the user says options are too far or asks for closer ones, "
    "search again with a tighter radius (e.g. within 1-2 miles) and avoid repeating places already mentioned. "
    "By default list at most 3 facilities; if the user explicitly asks for more, list as many as requested. "
    "IMPORTANT: Only include a facility if you have its complete street address (number, street, city, state, zip). "
    "If you cannot find the full address for a facility, skip it entirely and find a different one that has a confirmed address. "
    "Never output placeholder text like 'address not available' or 'cannot be found'. "
    "LOCATION NORMALIZATION: When the user mentions any location or address — even if informally written "
    "(e.g. '73000verano rd irvine ca', 'near UCI', 'downtown LA') — interpret it as a US address and output "
    "a single line at the very start of your response in exactly this format:\n"
    "User location: [normalized full address or city, state]\n"
    "For example: 'User location: 73000 Verano Rd, Irvine, CA 92617' or 'User location: Irvine, CA'. "
    "If no location is mentioned by the user, omit this line entirely.\n"
    "Format each facility entry exactly like this example:\n"
    "1. Clinic Name\n"
    "   Address: 123 Main St, City, CA 90000\n"
    "   Phone: (000) 000-0000\n\n"
    "After the list, add one short encouraging sentence reminding them to verify availability. "
    "Use plain text only, no markdown. Keep responses concise but warm."
)

SUMMARY_REQUEST = (
    "Please provide a warm, reassuring summary of these skin analysis results. "
    "Start by acknowledging that receiving results can feel worrying. "
    "Briefly explain what was detected and the risk level in simple, calm language. "
    "End with an encouraging next step. "
    "Keep it to 3-4 sentences. Plain text only, no bullet points."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context(results: list = None) -> str:
    ctx = SYSTEM_BASE
    if results:
        ctx += "\n\nCurrent analysis results:\n"
        for r in results:
            if "error" in r:
                ctx += f"- {r.get('filename', '?')}: analysis failed\n"
                continue
            top        = r.get("top_prediction", "?")
            risk_level = {"high": "requires urgent attention", "medium": "warrants further evaluation"}.get(r.get("risk_level", "low"), "appears low risk")
            ctotal     = r.get("cancer_total", 0)
            cancer_str = ", ".join(f"{k}={v}%" for k, v in r.get("cancer", {}).items())
            ctx += (
                f"- {r.get('filename', '?')}: top={top}, {risk_level}, "
                f"malignancy score={ctotal}%, breakdown=[{cancer_str}]\n"
            )
    else:
        ctx += "\n\nNo analysis results are available yet."
    return ctx


def _call(prompt: str, search: bool = False) -> str:
    """Single generate_content call with a plain string prompt."""
    cfg = types.GenerateContentConfig(temperature=TEMPERATURE)
    if search:
        cfg = types.GenerateContentConfig(
            temperature=TEMPERATURE,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=cfg,
    )
    text = response.text
    if text:
        return text
    try:
        candidate = response.candidates[0]
        print(f"[chatbot] finish_reason={candidate.finish_reason}")
        print(f"[chatbot] safety_ratings={candidate.safety_ratings}")
        part_text = candidate.content.parts[0].text
        if part_text:
            return part_text
    except Exception as e:
        print(f"[chatbot] inspection error: {e}")
    return ""


_US_STATE  = (r'(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT'
              r'|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)')
_ROAD_TYPE = r'(?:rd|st|ave|blvd|dr|way|ln|ct|pl|cir|pkwy|road|street|avenue|boulevard|drive)\.?'

def _extract_location(text: str) -> str | None:
    """Extract user location from message.
    Tries full street address first so house numbers like '73000' are not mistaken for zip codes.
    """
    # 1. Full street address: "123 Some Rd, City, CA[ 12345]"
    m = re.search(
        r'(\d+\s+\w[\w ]{2,40}' + _ROAD_TYPE +
        r'[,\s][\w\s,]{3,60}' + _US_STATE + r'(?:\s+\d{5})?)',
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    # 2. Zip clearly preceded by state abbreviation: "CA 92617"
    m = re.search(_US_STATE + r'\s*,?\s*(\d{5})\b', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # 3. Standalone zip — must not be immediately followed by a letter or space+letter
    #    (avoids treating "73000verano" or "73000 verano" as zip)
    m = re.search(r'(?<!\d)(\d{5})(?!\d)(?![A-Za-z])(?!\s+[A-Za-z])', text)
    if m:
        return m.group(1)
    return None


def _extract_ai_location(text: str) -> str | None:
    """Parse the 'User location: ...' line that the AI outputs when it detects a location."""
    m = re.search(r'^User location:\s*(.+)', text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    loc = m.group(1).strip().rstrip('.')
    if not loc or loc.lower() in ('unknown', 'not provided', 'none', 'n/a'):
        return None
    return loc


def _parse_facilities(text: str) -> list[dict]:
    """Parse numbered facility entries from formatted response text."""
    facilities = []
    current: dict = {}
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r'^\d+\.', stripped):
            if current.get('name'):
                facilities.append(current)
            current = {'name': re.sub(r'^\d+\.\s*', '', stripped)}
        elif stripped.startswith('Address:'):
            current['address'] = stripped[len('Address:'):].strip()
        elif stripped.startswith('Phone:'):
            current['phone'] = stripped[len('Phone:'):].strip()
    if current.get('name'):
        facilities.append(current)

    # Drop entries whose address is missing or a placeholder
    _BAD_ADDR = re.compile(
        r'^\s*$|无法|not (available|found|specified|provided)|'
        r'address unknown|n/?a\b|\(.*\)',
        re.IGNORECASE
    )
    return [f for f in facilities if f.get('address') and not _BAD_ADDR.search(f['address'])]


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(results: list) -> str:
    """One-shot summary of analysis results shown automatically after each scan."""
    ctx    = _build_context(results)
    prompt = f"{ctx}\n\n---\n{SUMMARY_REQUEST}"
    return _call(prompt)


_FACILITY_KEYWORDS = re.compile(
    r'hospital|clinic|dermatologist|doctor|facility|facilities|'
    r'nearest|closest|near me|nearby|around|close to|找医|附近|最近',
    re.IGNORECASE
)


def _format_facilities_prompt(fac_list: list[dict], user_location: str, n: int) -> str:
    """Build a prompt asking AI to warmly present pre-fetched facility data."""
    lines = [
        f"The user asked for the {n} nearest medical facilities to: {user_location}",
        "Here is the real distance-sorted data from OpenStreetMap. "
        "Present these results warmly and encouragingly. "
        "Use the exact names, addresses, phones, and distances provided — do not change or add any. "
        "Format each entry exactly as:\n"
        "N. Name\n"
        "   Address: ...\n"
        "   Phone: ...\n"
        "   Distance: X.X mi\n\n"
        "After the list add one short warm sentence encouraging them to call ahead.",
        "",
        "Facilities:",
    ]
    for i, f in enumerate(fac_list, 1):
        addr  = f.get("address") or "Address not available"
        phone = f.get("phone")   or "Phone not available"
        dist  = f.get("distance_mi", "?")
        lines.append(
            f"{i}. {f['name']}\n"
            f"   Address: {addr}\n"
            f"   Phone: {phone}\n"
            f"   Distance: {dist} mi"
        )
    return "\n".join(lines)


def _ai_normalize_location(text: str) -> str | None:
    """
    Ask Gemini (no search) to extract and standardize a US location from free-form text.
    Used as fallback when regex extraction fails (e.g. '73000verano rd irvine ca').
    """
    prompt = (
        "Extract the US location from the text below and return it as a standard address "
        "(e.g. '73000 Verano Rd, Irvine, CA 92617') or at minimum 'City, State'. "
        "Return ONLY the address string, no explanation. "
        "If no location is present, return NONE.\n\n"
        f"Text: {text}"
    )
    try:
        result = _call(prompt, search=False).strip().strip('"').strip("'")
        if not result or result.upper() == "NONE":
            return None
        return result
    except Exception:
        return None


def chat_reply(message: str, history: list, results: list = None) -> dict:
    """Multi-turn chat response. Returns reply text plus structured facility data."""

    # ── Deterministic facility lookup via Overpass API ────────────────────────
    asking_facilities = bool(_FACILITY_KEYWORDS.search(message))
    if asking_facilities:
        # 1. Try regex first (fast, no API call)
        raw_loc = (
            _extract_location(message)
            or _extract_location(" ".join(h["content"] for h in history if h["role"] == "user"))
        )
        # 2. Regex failed → ask AI to normalize the address (handles "73000verano rd irvine ca")
        if not raw_loc:
            raw_loc = _ai_normalize_location(message)
            if raw_loc:
                print(f"[chat] AI-normalized location: {raw_loc!r}")

        # How many facilities requested? default 4
        n_match = re.search(r'(\d+)\s*(?:家|个|places?|facilities|hospitals?|clinics?)', message, re.IGNORECASE)
        n_want  = int(n_match.group(1)) if n_match else 4

        if raw_loc:
            fac_list, coords = _fac.find_nearby(raw_loc, n=n_want)
            if fac_list:
                # Ask AI to format and warm up the pre-fetched data (no web search needed)
                ctx         = _build_context(results)
                fmt_prompt  = _format_facilities_prompt(fac_list, raw_loc, n_want)
                full_prompt = f"{ctx}\n\n---\n{fmt_prompt}\n\nAssistant:"
                reply       = _call(full_prompt, search=False)
                if reply.startswith("Assistant:"):
                    reply = reply[len("Assistant:"):].strip()

                # Attach user location string for map geocoding
                user_location = (
                    _extract_ai_location(reply)
                    or raw_loc
                )
                return {
                    "reply":         reply,
                    "facilities":    fac_list,
                    "user_location": user_location,
                }

    # ── Fallback: standard AI reply with web search ───────────────────────────
    ctx   = _build_context(results)
    lines = [ctx, "---"]
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"User: {message}")
    lines.append("Assistant:")
    prompt = "\n".join(lines)
    reply  = _call(prompt, search=True)
    if reply.startswith("Assistant:"):
        reply = reply[len("Assistant:"):].strip()

    parsed_fac = _parse_facilities(reply)
    if parsed_fac:
        user_location = (
            _extract_ai_location(reply)
            or _extract_location(message)
            or _extract_location(reply)
        )
    else:
        user_location = None

    return {
        "reply":         reply,
        "facilities":    parsed_fac,
        "user_location": user_location,
    }
