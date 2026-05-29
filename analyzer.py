"""
analyzer.py — Gemini Vision 皮肤病变分析
"""

import os
import json
import re
import time
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_config  = types.GenerateContentConfig(temperature=0)

MODEL                = "gemini-2.5-pro"
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

Also assess image quality:
- "lighting_ok": false if the image is too dark, overexposed, or lighting significantly impairs visibility of the lesion; true otherwise.
- "framing_ok": false if (1) skin or the lesion occupies less than roughly 30% of the image frame, leaving too much background, clothing, or non-skin area, OR (2) the image is cluttered with many irrelevant objects (e.g. furniture, multiple body parts unrelated to the lesion, busy backgrounds) that would confuse lesion analysis; true otherwise. A ruler or scale marker next to the lesion is acceptable.

You must respond in English only. Return ONLY a valid JSON object, no extra text:
{
  "MEL": <number>, "BCC": <number>, "AKIEC": <number>,
  "NV": <number>, "BKL": <number>, "DF": <number>, "VASC": <number>,
  "WART": <number>, "ECZEMA": <number>, "PSORIASIS": <number>,
  "ACNE": <number>, "SEBDERM": <number>, "ROSACEA": <number>,
  "TINEA": <number>, "VITILIGO": <number>, "OTHER": <number>,
  "lighting_ok": <true or false>,
  "framing_ok": <true or false>
}"""


def _parse_probabilities(text: str) -> tuple[dict[str, float], bool]:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    raw  = json.loads(text)
    probs = {k: float(raw[k]) for k in ALL_CLASSES if k in raw}
    missing = [k for k in ALL_CLASSES if k not in probs]
    if missing:
        raise ValueError(f"Response missing classes: {missing}")
    lighting_ok = bool(raw.get("lighting_ok", True))
    framing_ok  = bool(raw.get("framing_ok", True))
    return probs, lighting_ok, framing_ok


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


def _generate_with_retry(img, max_retries: int = 4, base_delay: float = 5.0):
    """Call the API with exponential backoff on 503 / rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return _client.models.generate_content(
                model=MODEL, contents=[img, PROMPT], config=_config
            )
        except Exception as e:
            msg = str(e)
            is_retryable = ("503" in msg or "UNAVAILABLE" in msg
                            or "429" in msg or "Resource has been exhausted" in msg)
            if is_retryable and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[analyzer] API {msg[:60]}… retrying in {delay:.0f}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise


def analyze_file(filepath: str, n_runs: int = N_RUNS) -> dict:
    """跑 n_runs 次，每个类别取最大概率后返回结果。"""
    img  = Image.open(filepath).convert("RGB")
    runs = []
    lighting_votes = []
    framing_votes  = []
    for _ in range(n_runs):
        response = _generate_with_retry(img)
        probs, lighting_ok, framing_ok = _parse_probabilities(response.text)
        runs.append(_normalize(probs))
        lighting_votes.append(lighting_ok)
        framing_votes.append(framing_ok)

    agg_probs = _aggregate_max(runs)
    result = _build_result(os.path.basename(filepath), agg_probs)
    majority = len(runs) / 2
    result["lighting_ok"] = (sum(lighting_votes) > majority)
    result["framing_ok"]  = (sum(framing_votes)  > majority)
    return result


