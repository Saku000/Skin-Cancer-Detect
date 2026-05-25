# Skin Cancer Detection

AI-powered skin lesion analysis using Gemini Vision. Upload dermoscopy images and get probability estimates across 16 categories, with malignancy risk assessment.

## Classes

**Malignant**

| Code | Full Name |
|------|-----------|
| MEL | Melanoma |
| BCC | Basal Cell Carcinoma |
| AKIEC | Actinic Keratosis / Squamous Cell Carcinoma |

**Benign — dermoscopic (ISIC)**

| Code | Full Name |
|------|-----------|
| NV | Melanocytic Nevi |
| BKL | Benign Keratosis-like Lesions |
| DF | Dermatofibroma |
| VASC | Vascular Lesions |

**Common skin conditions**

| Code | Full Name |
|------|-----------|
| WART | Wart / Verruca |
| ECZEMA | Eczema / Dermatitis |
| PSORIASIS | Psoriasis |
| ACNE | Acne |
| SEBDERM | Seborrheic Dermatitis |
| ROSACEA | Rosacea |
| TINEA | Tinea / Fungal Infection |
| VITILIGO | Vitiligo |
| OTHER | Other / Unclassified |

## Prerequisites

- Python 3.10 or higher
- A [Gemini API key](https://aistudio.google.com/app/apikey)

## Setup

### 1. Configure API Key

Create a `.env` file in the project folder:

```
GEMINI_API_KEY=your_api_key_here
```

### 2. Install Dependencies

**Windows**

Double-click `setup.bat`

**macOS**

```bash
chmod +x setup.sh start.sh
./setup.sh
```

## Running

**Windows**

Double-click `start.bat`

**macOS**

```bash
./start.sh
```

The app will start the server and open `http://127.0.0.1:8000/ui` in your browser automatically.

## Usage

1. Drag and drop skin lesion images into the upload zone, or click **Browse Files**
2. Click **Analyse Images**
3. Results show:
   - Risk level (High / Low)
   - Malignant class probabilities (MEL, BCC, AKIEC)
   - Benign class probabilities above 20%
   - Top prediction

Supported formats: JPG, PNG, WebP

## Notes

- This tool is for **research and educational purposes only**. It is not a medical diagnostic device.
- The model performs best with standard dermoscopy images. Regular photos may produce unreliable results.
- The dataset used for training (ISIC 2018/2019) does not include normal skin, so the model cannot identify healthy skin — it will always assign the image to one of the 7 lesion categories.
- Always consult a qualified dermatologist for clinical decisions.
