"""
app.py — Skin Lesion Detection Streamlit UI

Run:
    streamlit run app.py
"""

import os
import streamlit as st
from analyzer import analyze_file

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

CANCER_CLASSES = {"MEL", "BCC", "AKIEC"}
CLASS_LABEL = {
    "MEL":   "Melanoma (MEL)",
    "NV":    "Melanocytic Nevi (NV)",
    "BCC":   "Basal Cell Carcinoma (BCC)",
    "AKIEC": "Actinic Keratosis / SCC (AKIEC)",
    "BKL":   "Benign Keratosis (BKL)",
    "DF":    "Dermatofibroma (DF)",
    "VASC":  "Vascular Lesion (VASC)",
}

st.set_page_config(page_title="Skin Lesion Detection", page_icon="🔬", layout="wide")
st.title("🔬 Skin Lesion Detection")
st.caption("Upload skin lesion images and AI will analyse the probability of each condition.")

uploaded_files = st.file_uploader(
    "Select images (JPG / PNG / WebP, multiple files supported)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.divider()
    analyze_btn = st.button("Analyse", type="primary", use_container_width=True)

    if analyze_btn:
        for uploaded in uploaded_files:
            save_path = os.path.join(UPLOAD_DIR, uploaded.name)
            with open(save_path, "wb") as f:
                f.write(uploaded.getbuffer())

            st.subheader(f"📄 {uploaded.name}")
            col_img, col_result = st.columns([1, 2])

            with col_img:
                st.image(uploaded, use_container_width=True)

            with col_result:
                with st.spinner("Analysing..."):
                    try:
                        result = analyze_file(save_path)
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                        continue

                if result["is_high_risk"]:
                    st.error(f"⚠️ High Risk — Total malignant probability: {result['cancer_total']}%")
                else:
                    st.success(f"✅ Low Risk — Total malignant probability: {result['cancer_total']}%")

                st.markdown("**Malignant probabilities (always shown)**")
                for cls, prob in result["cancer"].items():
                    st.progress(
                        int(prob),
                        text=f"{CLASS_LABEL[cls]}: {prob:.1f}%",
                    )

                if result["non_cancer"]:
                    st.markdown("**Other conditions (shown only if >20%)**")
                    for cls, prob in result["non_cancer"].items():
                        st.progress(
                            int(prob),
                            text=f"{CLASS_LABEL[cls]}: {prob:.1f}%",
                        )

                st.caption(f"Top prediction: **{result['top_prediction']}**")

            st.divider()
