"""
analyzer.py — Gemini Vision 皮肤病变分析
"""

import os
import json
import re
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_config  = types.GenerateContentConfig(temperature=0)

MODEL                = "gemini-2.5-pro"
CHAT_MODEL           = "gemini-2.0-flash"
N_RUNS               = 3      # 每张图跑几次，每个类别取最大概率
CANCER_CLASSES       = {"MEL", "BCC", "AKIEC"}
ALL_CLASSES          = [
    # Malignant
    "MEL", "BCC", "AKIEC",
    # Benign — dermoscopic (ISIC)
    "NV", "BKL", "DF", "VASC",
    # Benign — common skin conditions
    "WART", "ECZEMA", "PSORIASIS", "ACNE", "SEBDERM", "ROSACEA", "TINEA", "VITILIGO",
    # Catch-all
    "OTHER",
]
NON_CANCER_THRESHOLD = 20.0

PROMPT = """You are a dermatology AI assistant specialized in skin condition analysis.

Analyze the skin image and estimate the probability (percentage, 0-100) that it belongs to each category below. Probabilities must sum to exactly 100.

Malignant:
- MEL: Melanoma — irregular pigmented lesion, asymmetry, varied color
- BCC: Basal Cell Carcinoma — pearly or translucent nodule, rolled border, telangiectasia
- AKIEC: Actinic Keratosis / Squamous Cell Carcinoma — rough scaly patch on sun-exposed skin

Benign (dermoscopic):
- NV: Melanocytic Nevi — common mole, uniform color and border
- BKL: Benign Keratosis-like Lesions — seborrheic keratosis, stuck-on waxy appearance
- DF: Dermatofibroma — firm nodule, often on legs, central white scar
- VASC: Vascular Lesions — angioma, hemangioma, bright red/purple vascular structures

Common skin conditions:
- WART: Wart / Verruca — rough cauliflower-like surface, HPV-related
- ECZEMA: Eczema / Dermatitis — red, itchy, inflamed, often with scaling or weeping
- PSORIASIS: Psoriasis — well-defined red plaques with silvery-white scales
- ACNE: Acne — comedones, papules, pustules, nodules on face/back/chest
- SEBDERM: Seborrheic Dermatitis — greasy yellowish scales on scalp, face, or chest
- ROSACEA: Rosacea — persistent facial redness, visible vessels, papules
- TINEA: Tinea / Fungal Infection — ring-like scaly patch, ringworm or athlete's foot
- VITILIGO: Vitiligo — depigmented white patches with sharp borders

Other:
- OTHER: Does not clearly match any category above, or image quality is insufficient

You must respond in English only. Return ONLY a valid JSON object, no extra text:
{
  "MEL": <number>, "BCC": <number>, "AKIEC": <number>,
  "NV": <number>, "BKL": <number>, "DF": <number>, "VASC": <number>,
  "WART": <number>, "ECZEMA": <number>, "PSORIASIS": <number>,
  "ACNE": <number>, "SEBDERM": <number>, "ROSACEA": <number>,
  "TINEA": <number>, "VITILIGO": <number>, "OTHER": <number>
}"""


def _parse_probabilities(text: str) -> dict[str, float]:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    raw  = json.loads(text)
    probs = {k: float(raw[k]) for k in ALL_CLASSES if k in raw}
    missing = [k for k in ALL_CLASSES if k not in probs]
    if missing:
        raise ValueError(f"Response missing classes: {missing}")
    return probs


def _normalize(probs: dict[str, float]) -> dict[str, float]:
    total = sum(probs.values())
    if total == 0:
        return {k: round(100 / len(probs), 2) for k in probs}
    return {k: round(v * 100 / total, 2) for k, v in probs.items()}


def _aggregate_max(runs: list[dict[str, float]]) -> dict[str, float]:
    """每个类别独立取所有 run 中的最大值，不做归一化。"""
    return {
        cls: round(max(r[cls] for r in runs), 2)
        for cls in ALL_CLASSES
    }


def _build_result(filename: str, probs: dict[str, float]) -> dict:
    cancer     = {k: probs[k] for k in ALL_CLASSES if k in CANCER_CLASSES}
    non_cancer = {
        k: probs[k] for k in ALL_CLASSES
        if k not in CANCER_CLASSES and probs[k] > NON_CANCER_THRESHOLD
    }
    top          = max(probs, key=probs.get)
    # 多次取 max 后各类别独立，cancer_total 用癌症类中的最高值
    cancer_total = round(max(cancer.values()), 2)
    return {
        "filename":       filename,
        "cancer":         cancer,
        "non_cancer":     non_cancer,
        "top_prediction": top,
        "cancer_total":   cancer_total,
        "is_high_risk":   cancer_total >= 50,
        "all_probs":      probs,
    }


def analyze_file(filepath: str, n_runs: int = N_RUNS) -> dict:
    """跑 n_runs 次，每个类别取最大概率后返回结果。"""
    img  = Image.open(filepath).convert("RGB")
    runs = []
    for _ in range(n_runs):
        response = _client.models.generate_content(
            model=MODEL, contents=[img, PROMPT], config=_config
        )
        probs = _normalize(_parse_probabilities(response.text))
        runs.append(probs)

    agg_probs = _aggregate_max(runs)
    return _build_result(os.path.basename(filepath), agg_probs)


# ── Chat ──────────────────────────────────────────────────────────

def _build_chat_system(results: list = None) -> str:
    prompt = (
        "You are a compassionate dermatology AI assistant. "
        "Help users understand their skin lesion analysis results clearly and calmly. "
        "Always recommend consulting a qualified dermatologist for any concerns. "
        "Never make definitive medical diagnoses. "
        "Respond in plain text without markdown formatting. Keep answers concise."
    )
    if results:
        prompt += "\n\nCurrent analysis results:\n"
        for r in results:
            if "error" in r:
                prompt += f"- {r.get('filename','?')}: analysis failed\n"
                continue
            top   = r.get("top_prediction", "?")
            risk  = "HIGH RISK" if r.get("is_high_risk") else "low risk"
            ctotal = r.get("cancer_total", 0)
            cancer_str = ", ".join(
                f"{k}={v}%" for k, v in r.get("cancer", {}).items()
            )
            prompt += (
                f"- {r.get('filename','?')}: top prediction={top}, {risk}, "
                f"cancer total={ctotal}%, cancer probs=[{cancer_str}]\n"
            )
    else:
        prompt += "\n\nNo analysis results are available yet."
    return prompt


def generate_summary(results: list) -> str:
    """根据检测结果生成一段自动摘要和建议。"""
    system = _build_chat_system(results)
    user_msg = (
        "Please provide a brief, friendly summary of these skin analysis results. "
        "Include what was detected, the overall risk level, and what the user should do next. "
        "Keep it to 3-4 sentences. Plain text only, no bullet points."
    )
    response = _client.models.generate_content(
        model=CHAT_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=user_msg)])],
        config=types.GenerateContentConfig(temperature=0.7),
    )
    return response.text


def chat_reply(message: str, history: list, results: list = None) -> str:
    """根据对话历史和当前检测结果生成回复。"""
    system   = _build_chat_system(results)
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    response = _client.models.generate_content(
        model=CHAT_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.7,
        ),
    )
    return response.text
