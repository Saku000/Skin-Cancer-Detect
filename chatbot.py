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
    "MAP TRIGGER: When the user is asking about nearby clinics, dermatologists, hospitals, or any medical facility, "
    "place the token [SHOW_MAP] on its own line at the very start of your response — before any other text. "
    "This token is hidden from the user and will trigger an interactive map; do not mention it. "
    "Only output [SHOW_MAP] when the user is genuinely requesting facility locations — not for general medical questions. "
    "LOCATION NORMALIZATION: When the user mentions any location or address — even if informally written "
    "(e.g. '73000verano rd irvine ca', 'near UCI', 'downtown LA') — interpret it as a US address and output "
    "a single line immediately after [SHOW_MAP] (or at the very start if no map) in exactly this format:\n"
    "User location: [normalized full address or city, state]\n"
    "For example: 'User location: 73000 Verano Rd, Irvine, CA 92617' or 'User location: Irvine, CA'. "
    "If no location is mentioned by the user, omit this line entirely.\n"
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


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(results: list) -> str:
    """One-shot summary of analysis results shown automatically after each scan."""
    ctx    = _build_context(results)
    prompt = f"{ctx}\n\n---\n{SUMMARY_REQUEST}"
    return _call(prompt)


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

    # ── Standard AI reply (model decides whether to output [SHOW_MAP]) ────────
    ctx   = _build_context(results)
    lines = [ctx, "---"]
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"User: {message}")
    lines.append("Assistant:")
    prompt = "\n".join(lines)
    # Disable web search: Overpass handles facility data; search causes garbled replies
    reply  = _call(prompt, search=False)
    if reply.startswith("Assistant:"):
        reply = reply[len("Assistant:"):].strip()

    # ── Detect [SHOW_MAP] token in model output ───────────────────────────────
    show_map = bool(re.search(r'\[SHOW_MAP\]', reply, re.IGNORECASE))
    # Extract location from AI reply BEFORE stripping hidden tokens
    loc_from_reply = _extract_ai_location(reply)
    # Strip hidden tokens and "User location:" line from displayed reply
    reply = re.sub(r'\[SHOW_MAP\]\s*\n?', '', reply, flags=re.IGNORECASE)
    reply = re.sub(r'User location:.*\n?', '', reply, flags=re.IGNORECASE).strip()

    if show_map:
        # Extract location: user message → history → AI-normalized location line
        raw_loc = (
            _extract_location(message)
            or _extract_location(" ".join(h["content"] for h in history if h["role"] == "user"))
            or loc_from_reply
        )
        if not raw_loc:
            raw_loc = _ai_normalize_location(message)
            if raw_loc:
                print(f"[chat] AI-normalized location: {raw_loc!r}")

        if raw_loc:
            n_match  = re.search(r'(\d+)\s*(?:家|个|places?|facilities|hospitals?|clinics?)', message, re.IGNORECASE)
            n_want   = int(n_match.group(1)) if n_match else 4
            fac_list, _ = _fac.find_nearby(raw_loc, n=n_want)
            if fac_list:
                return {
                    "reply":         reply,
                    "facilities":    fac_list,
                    "user_location": raw_loc,
                }

    return {
        "reply":         reply,
        "facilities":    [],
        "user_location": None,
    }
