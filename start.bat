@echo off
title KALA - Flagship E-Commerce & Multimodal AI Search
cd /d "%~dp0"
set "HF_HOME=%~dp0.cache\huggingface"
set "TORCH_HOME=%~dp0.cache\torch"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo ==============================================================
echo   KALA - Sistem Informasi E-Commerce ^& Pencarian Multimodal
echo   URL Toko  : http://localhost:8000
echo   URL Admin : http://localhost:8000/admin
echo ==============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Membuat virtual environment Python dan menginstal dependensi...
    python -m venv .venv
    .venv\Scripts\pip.exe install -r requirements.txt
)

if not exist "data\kala_store.db" (
    echo [1/2] Mengunduh katalog produk dan foto studio HD...
    .venv\Scripts\python.exe scripts\seed_products.py
)

if not exist "data\indices\clip-fast\image_embeddings.npy" (
    echo [2/2] Mengindeks vektor foto produk dengan Sentence Transformers...
    .venv\Scripts\python.exe scripts\build_index.py
)

echo Membuka http://localhost:8000 ...
start http://localhost:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
