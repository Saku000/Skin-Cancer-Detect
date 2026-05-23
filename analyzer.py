"""
analyzer.py — Gemini Vision 皮肤病变分析
"""

import os
import json
import re
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL                = "gemini-2.5-pro"
CANCER_CLASSES       = {"MEL", "BCC", "AKIEC"}
ALL_CLASSES          = ["MEL", "NV", "BCC", "AKIEC", "BKL", "DF", "VASC"]
NON_CANCER_THRESHOLD = 20.0

PROMPT = """You are a dermatology AI assistant specialized in skin lesion analysis.

Analyze the skin lesion image and estimate the probability (percentage, 0-100) that it belongs to each category. Probabilities must sum to exactly 100.

Categories:
- MEL: Melanoma (malignant)
- NV: Melanocytic Nevi / moles (benign)
- BCC: Basal Cell Carcinoma (malignant)
- AKIEC: Actinic Keratosis / Squamous Cell Carcinoma (malignant/pre-malignant)
- BKL: Benign Keratosis-like Lesions (benign)
- DF: Dermatofibroma (benign)
- VASC: Vascular Lesions (benign)

You must respond in English only. Return ONLY a valid JSON object, no extra text:
{
  "MEL": <number>,
  "NV": <number>,
  "BCC": <number>,
  "AKIEC": <number>,
  "BKL": <number>,
  "DF": <number>,
  "VASC": <number>
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
    model    = genai.GenerativeModel(MODEL)
    response = model.generate_content([img, PROMPT])
    probs    = _parse_probabilities(response.text)
    probs    = _normalize(probs)
    return _build_result(os.path.basename(filepath), probs)
