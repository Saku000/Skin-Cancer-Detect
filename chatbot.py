"""
chatbot.py — AI assistant chat logic for skin lesion results

Endpoints consumed:
    POST /chat          -> chat_reply()
    POST /chat/summary  -> generate_summary()
"""

import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ── Config ────────────────────────────────────────────────────────────────────

MODEL       = "gemini-2.5-flash"
TEMPERATURE = 0.7

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
    "use your search capability to find real, specific options near their location. "
    "List at most 3 facilities. Format each entry exactly like this example:\n"
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
            risk_level = "requires urgent attention" if r.get("is_high_risk") else "appears low risk"
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

    # Log why it's empty
    try:
        candidate = response.candidates[0]
        print(f"[chatbot] finish_reason={candidate.finish_reason}")
        print(f"[chatbot] safety_ratings={candidate.safety_ratings}")
        # Try extracting text directly from parts
        part_text = candidate.content.parts[0].text
        if part_text:
            return part_text
    except Exception as e:
        print(f"[chatbot] inspection error: {e}")
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(results: list) -> str:
    """One-shot summary of analysis results shown automatically after each scan."""
    ctx    = _build_context(results)
    prompt = f"{ctx}\n\n---\n{SUMMARY_REQUEST}"
    return _call(prompt)


def chat_reply(message: str, history: list, results: list = None) -> str:
    """Multi-turn chat response. History is formatted as plain text in the prompt."""
    ctx   = _build_context(results)
    lines = [ctx, "---"]
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    lines.append(f"User: {message}")
    lines.append("Assistant:")
    prompt = "\n".join(lines)
    reply = _call(prompt, search=True)
    # Strip any leading "Assistant:" the model might echo back
    if reply.startswith("Assistant:"):
        reply = reply[len("Assistant:"):].strip()
    return reply
