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

SUMMARY_REQUEST = (
    "Please provide a brief, friendly summary of these skin analysis results. "
    "Include what was detected, the overall risk level, and what the user should do next. "
    "Keep it to 3-4 sentences. Plain text only, no bullet points."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_system_prompt(results: list = None) -> str:
    prompt = SYSTEM_BASE
    if results:
        prompt += "\n\nCurrent analysis results:\n"
        for r in results:
            if "error" in r:
                prompt += f"- {r.get('filename', '?')}: analysis failed\n"
                continue
            top        = r.get("top_prediction", "?")
            risk       = "HIGH RISK" if r.get("is_high_risk") else "low risk"
            ctotal     = r.get("cancer_total", 0)
            cancer_str = ", ".join(f"{k}={v}%" for k, v in r.get("cancer", {}).items())
            prompt += (
                f"- {r.get('filename', '?')}: top prediction={top}, {risk}, "
                f"cancer total={ctotal}%, cancer probs=[{cancer_str}]\n"
            )
    else:
        prompt += "\n\nNo analysis results are available yet."
    return prompt


def _make_config(system: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=TEMPERATURE,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(results: list) -> str:
    """One-shot summary of analysis results shown automatically after each scan."""
    system = _build_system_prompt(results)
    response = _client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=SUMMARY_REQUEST)])],
        config=_make_config(system),
    )
    return response.text


def chat_reply(message: str, history: list, results: list = None) -> str:
    """Multi-turn chat response with full conversation history and analysis context."""
    system   = _build_system_prompt(results)
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=_make_config(system),
    )
    return response.text
