"""
Script Pengindeks Vektor Multimodal di GPU (RTX 3050).
Menghasilkan file image_embeddings.npy & text_embeddings.npy untuk seluruh foto produk di database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("HF_HOME", str(BASE_DIR / ".cache" / "huggingface"))

from ai_engine.multimodal_retriever import MultimodalSearchEngine
from app.database import get_all_products_for_indexing, init_db


def main() -> None:
    init_db()
    products = get_all_products_for_indexing()
    if not products:
        print("Database produk masih kosong. Jalankan scripts/seed_products.py terlebih dahulu.")
        return

    engine = MultimodalSearchEngine()
    print(f"Memulai indexing {len(products)} foto produk menggunakan profil: {engine.profile['label']}...")
    stats = engine.build_product_index(products, batch_size=32)
    print(
        f"Indeks selesai! {stats['indexed']} produk terindeks di {stats['gpu_name']} ({stats['device']}) "
        f"dalam {stats['elapsed_sec']} detik."
    )


if __name__ == "__main__":
    main()
