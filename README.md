# Skin Lesion Detection

AI-powered skin cancer screening using Gemini Vision. Upload dermoscopy or clinical images and get independent probability estimates for three malignant conditions, with automatic image quality gating.

## Live Demo

| Platform | URL |
|----------|-----|
| Desktop | https://skin-cancer-detect.onrender.com/ui/index.html |
| Mobile  | https://skin-cancer-detect.onrender.com/ui/mobile.html |

> First load may take ~30 seconds (free tier cold start).

## Detected Conditions

| Code | Full Name | Type |
|------|-----------|------|
| MEL | Melanoma | Malignant |
| BCC | Basal Cell Carcinoma | Malignant |
| AKIEC | Actinic Keratosis / Squamous Cell Carcinoma | Malignant |

## Risk Levels

| Level | Threshold |
|-------|-----------|
| Low | < 15% |
| Medium | 15 – 30% |
| High | > 30% |

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

**macOS / Linux**

```bash
chmod +x setup.sh start.sh
./setup.sh
```

## Running

**Windows**

Double-click `start.bat`

**macOS / Linux**

```bash
./start.sh
```

The app starts the server and opens `http://127.0.0.1:8000/ui` in your browser.

## Usage

1. Drag and drop skin lesion images into the upload zone, or click **Browse Files**
2. Click **Analyse Images**
3. Images with poor lighting or framing are automatically rejected with a retake prompt
4. Results show:
   - Risk level (Low / Medium / High)
   - Independent probability for each malignant class
   - Top prediction

Supported formats: JPG, PNG, WebP

## Notes

- This tool is for **research and educational purposes only**. It is not a medical diagnostic device.
- Always consult a qualified dermatologist for clinical decisions.
