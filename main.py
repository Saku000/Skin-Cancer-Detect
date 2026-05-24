"""
main.py — 皮肤病变检测后端

启动：
    uvicorn main:app --reload --port 8000

接口：
    POST   /upload              上传一张或多张图片到 uploads/ 文件夹
    GET    /files               查看 uploads/ 里当前的图片列表
    POST   /analyze             分析 uploads/ 里的所有图片
    POST   /analyze/{filename}  分析 uploads/ 里指定的某张图片
    DELETE /clear               清空 uploads/ 文件夹
"""

import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List

from analyzer import analyze_file

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="皮肤病变检测 API", version="1.0.0")


@app.on_event("startup")
def clear_on_startup():
    for fname in os.listdir(UPLOAD_DIR):
        if os.path.splitext(fname)[1].lower() in ALLOWED_EXT:
            os.remove(os.path.join(UPLOAD_DIR, fname))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

WEB_UI_DIR = os.path.join(BASE_DIR, "web_ui")
app.mount("/ui", StaticFiles(directory=WEB_UI_DIR, html=True), name="web_ui")


# ── 工具函数 ──────────────────────────────────────────────

def _list_images() -> list[str]:
    return sorted(
        f for f in os.listdir(UPLOAD_DIR)
        if os.path.splitext(f)[1].lower() in ALLOWED_EXT
    )


# ── 接口 ──────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    """上传一张或多张图片，保存到 uploads/ 文件夹。"""
    saved = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(
                status_code=415,
                detail=f"{f.filename} 格式不支持，请上传 JPG / PNG / WebP",
            )
        dest = os.path.join(UPLOAD_DIR, f.filename)
        with open(dest, "wb") as out:
            out.write(await f.read())
        saved.append(f.filename)

    return {
        "uploaded": saved,
        "total_in_folder": len(_list_images()),
    }


@app.get("/files")
def list_files():
    """列出 uploads/ 文件夹里的所有图片。"""
    images = _list_images()
    return {"files": images, "count": len(images)}


@app.post("/analyze")
def analyze_all():
    """分析 uploads/ 文件夹里的所有图片。"""
    images = _list_images()
    if not images:
        raise HTTPException(status_code=404, detail="uploads/ 文件夹为空，请先上传图片")

    results = []
    for fname in images:
        path = os.path.join(UPLOAD_DIR, fname)
        try:
            results.append(analyze_file(path))
        except Exception as e:
            results.append({"filename": fname, "error": str(e)})

    return {"results": results, "total": len(results)}


@app.post("/analyze/{filename}")
def analyze_one(filename: str):
    """分析 uploads/ 文件夹里的指定图片。"""
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"找不到文件：{filename}")
    if os.path.splitext(filename)[1].lower() not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail="文件格式不支持")

    try:
        return analyze_file(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clear")
def clear_uploads():
    """清空 uploads/ 文件夹。"""
    removed = _list_images()
    for fname in removed:
        os.remove(os.path.join(UPLOAD_DIR, fname))
    return {"cleared": removed, "count": len(removed)}
