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

MODEL       = "gemini-2.0-flash"
TEMPERATURE = 0.7

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are a compassionate dermatology AI assistant. "
    "Help users understand their skin lesion analysis results clearly and calmly. "
    "Always recommend consulting a qualified dermatologist for any concerns. "
    "Never make definitive medical diagnoses. "
    "Respond in plain text without markdown formatting. Keep answers concise."
)

SYSTEM_ACK = "Understood. I will follow these guidelines and help users understand their results."

SUMMARY_REQUEST = (
    "Please provide a brief, friendly summary of these skin analysis results. "
    "Include what was detected, the overall risk level, and what the user should do next. "
    "Keep it to 3-4 sentences. Plain text only, no bullet points."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context(results: list = None) -> str:
    """Builds the system context string including current analysis results."""
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


def _context_pair(results: list = None) -> list:
    """Returns [user_context_msg, model_ack_msg] to inject context without system_instruction."""
    ctx = _build_context(results)
    return [
        types.Content(role="user",  parts=[types.Part(text=ctx)]),
        types.Content(role="model", parts=[types.Part(text=SYSTEM_ACK)]),
    ]


def _extract_text(response) -> str:
    """Safely extracts text from a Gemini response, logging issues if empty."""
    if response.text:
        return response.text
    try:
        text = response.candidates[0].content.parts[0].text
        if text:
            return text
    except Exception:
        pass
    try:
        finish = response.candidates[0].finish_reason
        safety = response.candidates[0].safety_ratings
        print(f"[chatbot] empty response — finish_reason={finish}, safety={safety}")
    except Exception as e:
        print(f"[chatbot] could not inspect response: {e}")
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(results: list) -> str:
    """One-shot summary of analysis results shown automatically after each scan."""
    contents = _context_pair(results) + [
        types.Content(role="user", parts=[types.Part(text=SUMMARY_REQUEST)]),
    ]
    response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(temperature=TEMPERATURE),
    )
    return _extract_text(response)


def chat_reply(message: str, history: list, results: list = None) -> str:
    """Multi-turn chat response with full conversation history and analysis context."""
    contents = _context_pair(results)
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(temperature=TEMPERATURE),
    )
    return _extract_text(response)
