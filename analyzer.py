"""
analyzer.py — Gemini Vision 皮肤病变分析
"""

import os
import json
import re
from google import genai
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL                = "gemini-2.5-pro"
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


def _build_result(filename: str, probs: dict[str, float]) -> dict:
    cancer     = {k: probs[k] for k in ALL_CLASSES if k in CANCER_CLASSES}
    non_cancer = {
        k: probs[k] for k in ALL_CLASSES
        if k not in CANCER_CLASSES and probs[k] > NON_CANCER_THRESHOLD
    }
    top          = max(probs, key=probs.get)
    cancer_total = round(sum(cancer.values()), 2)
    return {
        "filename":       filename,
        "cancer":         cancer,
        "non_cancer":     non_cancer,
        "top_prediction": top,
        "cancer_total":   cancer_total,
        "is_high_risk":   cancer_total >= 50,
        "all_probs":      probs,
    }


def analyze_file(filepath: str) -> dict:
    """从磁盘读取图片文件并分析。"""
    img      = Image.open(filepath).convert("RGB")
    response = _client.models.generate_content(model=MODEL, contents=[img, PROMPT])
    probs    = _parse_probabilities(response.text)
    probs    = _normalize(probs)
    return _build_result(os.path.basename(filepath), probs)
