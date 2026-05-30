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
CANCER_CLASSES = {"MEL", "BCC", "AKIEC"}
ALL_CLASSES    = ["MEL", "BCC", "AKIEC"]

PROMPT = """You are a dermatology AI assistant specialized in skin cancer screening.

For the skin image provided, estimate the independent probability (0–100) that it shows each of the three malignant conditions below. Each is an independent estimate — they do NOT need to sum to 100.

- MEL: Melanoma — irregular pigmented lesion, asymmetry, varied color, irregular border
- BCC: Basal Cell Carcinoma — pearly or translucent nodule, rolled border, telangiectasia
- AKIEC: Actinic Keratosis / Squamous Cell Carcinoma — rough scaly patch on sun-exposed skin

Also assess image quality:
- "lighting_ok": false if the image is too dark, overexposed, or lighting significantly impairs visibility of the lesion; true otherwise.
- "framing_ok": false if (1) skin or the lesion occupies less than roughly 30% of the image frame, leaving too much background, clothing, or non-skin area, OR (2) the image is cluttered with many irrelevant objects that would confuse lesion analysis; true otherwise. A ruler or scale marker next to the lesion is acceptable.

You must respond in English only. Return ONLY a valid JSON object, no extra text:
{
  "MEL": <number>, "BCC": <number>, "AKIEC": <number>,
  "lighting_ok": <true or false>,
  "framing_ok": <true or false>
}"""


def _parse_probabilities(text: str) -> tuple[dict[str, float], bool, bool]:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    raw  = json.loads(text)
    probs = {k: float(raw[k]) for k in ALL_CLASSES if k in raw}
    missing = [k for k in ALL_CLASSES if k not in probs]
    if missing:
        raise ValueError(f"Response missing classes: {missing}")
    lighting_ok = bool(raw.get("lighting_ok", True))
    framing_ok  = bool(raw.get("framing_ok", True))
    return probs, lighting_ok, framing_ok


def _aggregate_max(runs: list[dict[str, float]]) -> dict[str, float]:
    """每个类别独立取所有 run 中的最大值。"""
    return {
        cls: round(max(r[cls] for r in runs), 2)
        for cls in ALL_CLASSES
    }


def _risk_level(cancer_total: float) -> str:
    if cancer_total >= 30:
        return "high"
    if cancer_total >= 15:
        return "medium"
    return "low"


def _build_result(filename: str, probs: dict[str, float]) -> dict:
    top          = max(probs, key=probs.get)
    cancer_total = round(max(probs.values()), 2)
    return {
        "filename":       filename,
        "cancer":         probs,
        "top_prediction": top,
        "cancer_total":   cancer_total,
        "risk_level":     _risk_level(cancer_total),
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
    """Run n_runs passes; first pass also acts as a quality gate."""
    img   = Image.open(filepath).convert("RGB")
    fname = os.path.basename(filepath)

    # First run — quality gate
    response = _generate_with_retry(img)
    probs, lighting_ok, framing_ok = _parse_probabilities(response.text)

    if not lighting_ok or not framing_ok:
        return {
            "filename":    fname,
            "lighting_ok": lighting_ok,
            "framing_ok":  framing_ok,
            "skipped":     True,
        }

    runs           = [probs]
    lighting_votes = [lighting_ok]
    framing_votes  = [framing_ok]

    for _ in range(n_runs - 1):
        response = _generate_with_retry(img)
        probs, lighting_ok, framing_ok = _parse_probabilities(response.text)
        runs.append(probs)
        lighting_votes.append(lighting_ok)
        framing_votes.append(framing_ok)

    agg_probs = _aggregate_max(runs)
    result    = _build_result(fname, agg_probs)
    majority  = len(runs) / 2
    result["lighting_ok"] = (sum(lighting_votes) > majority)
    result["framing_ok"]  = (sum(framing_votes)  > majority)
    return result


