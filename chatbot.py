"""
chatbot.py — AI assistant chat logic for skin lesion results

Endpoints consumed:
    POST /chat          -> chat_reply()  returns dict with reply + facilities
    POST /chat/summary  -> generate_summary()
"""

import json
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
    "Always do your best to answer whatever the user asks — never deflect or refuse unless the request is harmful. "
    "If the answer is in the conversation context, use it. "
    "If you are uncertain, say so honestly rather than giving a vague non-answer. "
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
    "Please provide a warm summary of these skin analysis results. "
    "IMPORTANT: Only mention a specific condition (MEL, BCC, AKIEC) by name if its probability is above 15%. "
    "Do NOT list conditions with zero or near-zero scores. "
    "If the overall risk level is LOW: lead with great news and a celebratory, relieved tone — tell the user their results look reassuring and there is no significant sign of concern. Keep it upbeat and positive. "
    "If the overall risk level is MEDIUM or HIGH: start by acknowledging results can feel worrying, describe the finding calmly, and end with an encouraging next step. "
    "Keep it to 2-3 sentences. Plain text only, no bullet points."
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
            if r.get("skipped"):
                reasons = []
                if not r.get("lighting_ok", True): reasons.append("poor lighting")
                if not r.get("framing_ok",  True): reasons.append("poor framing/coverage")
                ctx += f"- {r.get('filename', '?')}: analysis skipped ({', '.join(reasons)}) — ask user to retake\n"
                continue
            top        = r.get("top_prediction", "?")
            risk_level = {"high": "requires urgent attention", "medium": "warrants further evaluation"}.get(r.get("risk_level", "low"), "appears low risk")
            ctotal     = r.get("cancer_total", 0)
            notable    = {k: v for k, v in r.get("cancer", {}).items() if v >= 15}
            cancer_str = ", ".join(f"{k}={v}%" for k, v in notable.items()) if notable else "none above 15%"
            ctx += (
                f"- {r.get('filename', '?')}: {risk_level}, "
                f"malignancy score={ctotal}%, notable findings=[{cancer_str}]\n"
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


def _detect_intent(message: str, history: list) -> dict:
    """
    Ask Gemini (no search) to detect whether the user wants nearby medical facilities
    and extract their location. Returns {"wants_facilities": bool, "user_location": str|None}.
    This replaces the keyword list so informal, multilingual, or atypical phrasing still works.
    """
    recent = "\n".join(
        f"{h['role']}: {h['content']}" for h in history[-4:]
    ) if history else "(none)"
    prompt = (
        "Analyze the latest user message and recent history below.\n"
        "Return ONLY a JSON object — no explanation, no markdown:\n"
        '{"wants_facilities": true/false, "user_location": "City, State or full address or null", "n": 4}\n\n'
        "Rules:\n"
        "- wants_facilities = true if the user wants to find nearby hospitals, clinics, "
        "dermatologists, or any medical facility.\n"
        "- user_location = the place the user wants to search NEAR (their own location, "
        "NOT a facility they are asking about). Normalize to standard US format even if "
        "written informally or with typos — e.g. '73000verano irvine' → '73000 Verano Rd, Irvine, CA', "
        "'near UCI' → 'University of California Irvine, CA', 'downtown LA' → 'Los Angeles, CA'. "
        "Return the most specific address you can infer. null if no location is mentioned.\n"
        "- n = how many facilities the user wants (default 4 if unspecified).\n\n"
        f"Recent history:\n{recent}\n\n"
        f"Latest message: {message}"
    )
    try:
        raw = _call(prompt, search=False).strip()
        m   = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "wants_facilities": bool(data.get("wants_facilities")),
                "user_location":    data.get("user_location") or None,
                "n":                int(data.get("n", 4)),
            }
    except Exception as e:
        print(f"[chat] intent detection failed: {e}")
    return {"wants_facilities": False, "user_location": None, "n": 4}


def _find_facilities_via_ai(location: str, n: int) -> list[dict]:
    """Gemini web-search fallback when Overpass returns nothing."""
    prompt = (
        f"Search for the {n} nearest dermatology clinics, skin cancer centers, or hospitals "
        f"to: {location}\n"
        "Return ONLY a JSON array — no explanation, no markdown. Each element:\n"
        '{"name": "...", "address": "123 Main St, City, CA 90000", "phone": "(000) 000-0000"}\n'
        "Only include facilities with a confirmed full street address. Order by distance, closest first."
    )
    try:
        raw = _call(prompt, search=True).strip()
        m   = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return [
                d for d in data
                if isinstance(d, dict) and d.get("name") and d.get("address")
            ][:n]
    except Exception as e:
        print(f"[chat] AI facility search failed: {e}")
    return []


def _format_facilities_prompt(fac_list: list[dict], user_location: str, n: int, user_message: str) -> str:
    """Build a prompt asking AI to address the user's full message and include facility data."""
    lines = [
        f"The user's message: \"{user_message}\"",
        "",
        "Respond to everything the user asked above, warmly and in order.",
        f"As part of your response, include the {n} nearest medical facilities to {user_location} "
        "using the data below. Use the exact names, addresses, phones, and distances provided — "
        "do not change or add any. Omit the Distance line if not available. "
        "Format each facility as:",
        "N. Name",
        "   Address: ...",
        "   Phone: ...",
        "   Distance: X.X mi",
        "",
        "End with one short warm sentence encouraging them to call ahead.",
        "Plain text only, no markdown.",
        "",
        "Facilities:",
    ]
    for i, f in enumerate(fac_list, 1):
        addr  = f.get("address") or "Address not available"
        phone = f.get("phone")   or "Phone not available"
        dist  = f.get("distance_mi")
        entry = f"{i}. {f['name']}\n   Address: {addr}\n   Phone: {phone}"
        if dist is not None:
            entry += f"\n   Distance: {dist} mi"
        lines.append(entry)
    return "\n".join(lines)



def chat_reply(message: str, history: list, results: list = None) -> dict:
    """Multi-turn chat response. Returns reply text plus structured facility data."""

    # ── Step 1: Gemini intent detection (no search, not shown to user) ────────
    intent = _detect_intent(message, history)
    print(f"[chat] intent={intent}")

    if intent["wants_facilities"] and intent["user_location"]:
        raw_loc = intent["user_location"]
        n_want  = intent["n"]

        # ── Step 2: Overpass (fast, deterministic) ────────────────────────────
        print(f"[chat] Overpass query: {raw_loc!r} n={n_want}")
        fac_list, coords = _fac.find_nearby(raw_loc, n=n_want)
        print(f"[chat] Overpass returned {len(fac_list)} facilities")

        # ── Step 3: AI web-search fallback if Overpass empty ─────────────────
        if not fac_list:
            print("[chat] Overpass empty — trying AI web search")
            fac_list = _find_facilities_via_ai(raw_loc, n_want)
            print(f"[chat] AI search returned {len(fac_list)} facilities")

        if fac_list:
            ctx         = _build_context(results)
            hist_lines  = "\n".join(
                f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
                for h in history
            )
            fmt_prompt  = _format_facilities_prompt(fac_list, raw_loc, n_want, message)
            full_prompt = (
                f"{ctx}\n\n---\n"
                + (f"{hist_lines}\n" if hist_lines else "")
                + f"{fmt_prompt}\n\nAssistant:"
            )
            reply       = _call(full_prompt, search=False)
            if reply.startswith("Assistant:"):
                reply = reply[len("Assistant:"):].strip()
            reply = re.sub(r'User location:.*\n?', '', reply, flags=re.IGNORECASE).strip()
            return {
                "reply":         reply,
                "facilities":    fac_list,
                "user_location": raw_loc,
            }

        # Both Overpass and AI search failed
        return {
            "reply": (
                "I wasn't able to find nearby facilities right now. "
                "Please try searching Google Maps for dermatologists or hospitals near your location."
            ),
            "facilities":    [],
            "user_location": None,
        }

    # ── Standard AI reply (no facility lookup needed) ─────────────────────────
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
    reply = re.sub(r'User location:.*\n?', '', reply, flags=re.IGNORECASE).strip()
    return {
        "reply":         reply,
        "facilities":    [],
        "user_location": None,
    }
