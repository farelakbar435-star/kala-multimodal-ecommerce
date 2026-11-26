"""
Script Otomatis Pengisi Katalog Produk & Foto Studio HD (Auto-Seeder HD 900x1200)
Mengambil produk fashion asli beresolusi tinggi (900x1200 piksel) dari Hugging Face
(benitomartin/fashion-product-images-small-900x1200), menerjemahkan atribut ke Bahasa Indonesia,
menyimpan ke SQLite, serta menyiapkan dataset benchmark NDCG@10 & pasangan finetuning.
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("HF_HOME", str(BASE_DIR / ".cache" / "huggingface"))

from PIL import Image
from app.database import create_product, get_connection, init_db

PRODUCTS_IMG_DIR = BASE_DIR / "app" / "static" / "products"
DATA_DIR = BASE_DIR / "data"

CATEGORY_MAP: dict[str, tuple[str, str, tuple[int, int]]] = {
    "Shirts": ("Pakaian Atas", "Kemeja", (179000, 349000)),
    "Tshirts": ("Pakaian Atas", "Kaos", (99000, 219000)),
    "Tops": ("Pakaian Atas", "Atasan Blus", (139000, 279000)),
    "Sweatshirts": ("Pakaian Atas", "Sweater & Hoodie", (219000, 399000)),
    "Jackets": ("Pakaian Atas", "Jaket", (289000, 549000)),
    "Sweaters": ("Pakaian Atas", "Sweater Rajut", (209000, 369000)),
    "Dresses": ("Pakaian Atas", "Gaun", (249000, 489000)),
    "Jeans": ("Celana & Bawahan", "Celana Jeans", (249000, 459000)),
    "Trousers": ("Celana & Bawahan", "Celana Panjang", (219000, 389000)),
    "Shorts": ("Celana & Bawahan", "Celana Pendek", (129000, 229000)),
    "Track Pants": ("Celana & Bawahan", "Celana Training", (159000, 279000)),
    "Skirts": ("Celana & Bawahan", "Rok", (169000, 299000)),
    "Casual Shoes": ("Sepatu & Alas Kaki", "Sepatu Kasual", (299000, 599000)),
    "Sports Shoes": ("Sepatu & Alas Kaki", "Sepatu Olahraga", (349000, 749000)),
    "Formal Shoes": ("Sepatu & Alas Kaki", "Sepatu Formal", (369000, 689000)),
    "Heels": ("Sepatu & Alas Kaki", "Sepatu Hak", (259000, 499000)),
    "Sandals": ("Sepatu & Alas Kaki", "Sandal", (119000, 249000)),
    "Flip Flops": ("Sepatu & Alas Kaki", "Sandal Santai", (79000, 149000)),
    "Backpacks": ("Tas & Ransel", "Tas Ransel", (229000, 499000)),
    "Handbags": ("Tas & Ransel", "Tas Tangan", (259000, 569000)),
    "Clutches": ("Tas & Ransel", "Dompet Pesta", (149000, 299000)),
    "Wallets": ("Tas & Ransel", "Dompet Kulit", (129000, 269000)),
    "Laptop Bag": ("Tas & Ransel", "Tas Laptop", (269000, 529000)),
    "Watches": ("Jam Tangan & Aksesoris", "Jam Tangan", (329000, 899000)),
    "Sunglasses": ("Jam Tangan & Aksesoris", "Kacamata Hitam", (149000, 349000)),
    "Belts": ("Jam Tangan & Aksesoris", "Ikat Pinggang", (119000, 239000)),
}

COLOR_MAP: dict[str, str] = {
    "Navy Blue": "Biru Dongker",
    "Blue": "Biru",
    "Black": "Hitam",
    "White": "Putih",
    "Grey": "Abu-abu",
    "Charcoal": "Abu-abu Tua",
    "Red": "Merah",
    "Maroon": "Merah Marun",
    "Green": "Hijau",
    "Olive": "Hijau Zaitun",
    "Teal": "Hijau Toska",
    "Brown": "Coklat",
    "Tan": "Coklat Muda",
    "Beige": "Krem",
    "Cream": "Krem Muda",
    "Pink": "Merah Muda",
    "Purple": "Ungu",
    "Lavender": "Ungu Muda",
    "Yellow": "Kuning",
    "Mustard": "Kuning Mustard",
    "Orange": "Oranye",
    "Silver": "Perak",
    "Gold": "Emas",
    "Multi": "Kombinasi Warna",
}

GENDER_MAP: dict[str, str] = {
    "Men": "Pria",
    "Women": "Wanita",
    "Boys": "Pria",
    "Girls": "Wanita",
    "Unisex": "Unisex",
}

USAGE_MAP: dict[str, str] = {
    "Casual": "Kasual",
    "Formal": "Formal",
    "Sports": "Olahraga",
    "Ethnic": "Etnik",
    "Smart Casual": "Semi Formal",
    "Party": "Pesta",
    "Travel": "Travel",
}

SERIES_LABELS = [
    "Seri Nusantara",
    "Koleksi Studio",
    "Edisi Urban",
    "Lini Klasik",
    "Seri Esensial",
    "Koleksi Signature",
    "Edisi Metro",
    "Seri Harmoni",
]


def detect_visual_pattern_id(en_title: str) -> str:
    low = en_title.lower()
    if any(w in low for w in ["check", "plaid", "gingham"]):
        return "motif kotak-kotak"
    if "strip" in low:
        return "motif garis"
    if any(w in low for w in ["floral", "flower"]):
        return "motif bunga"
    if "print" in low or "graphic" in low:
        return "bermotif grafis"
    if "leather" in low:
        return "bahan kulit"
    if "denim" in low:
        return "bahan denim"
    if "canvas" in low:
        return "bahan kanvas"
    return ""


def fetch_hd_candidates_via_api(target_total: int = 240) -> list[dict[str, Any]]:
    """Mengambil metadata + URL gambar studio HD 900x1200 langsung dari Hugging Face Datasets Server."""
    major_categories = [
        "Pakaian Atas",
        "Celana & Bawahan",
        "Sepatu & Alas Kaki",
        "Tas & Ransel",
        "Jam Tangan & Aksesoris",
    ]
    per_cat_quota = max(10, target_total // len(major_categories))
    cat_counts = {c: 0 for c in major_categories}
    candidates: list[dict[str, Any]] = []

    ds_name = "benitomartin/fashion-product-images-small-900x1200"
    offset = 0
    batch_len = 100

    while len(candidates) < target_total and offset < 3500:
        api_url = (
            f"https://datasets-server.huggingface.co/rows?"
            f"dataset={urllib.parse.quote(ds_name)}&config=default&split=train"
            f"&offset={offset}&length={batch_len}"
        )
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        rows = payload.get("rows", [])
        if not rows:
            break

        for item in rows:
            if len(candidates) >= target_total:
                break
            row = item.get("row", {})
            article_type = str(row.get("articleType") or "").strip()
            if article_type not in CATEGORY_MAP:
                continue

            major_cat, sub_cat_id, price_range = CATEGORY_MAP[article_type]
            if cat_counts[major_cat] >= per_cat_quota:
                continue

            en_color = str(row.get("baseColour") or "").strip()
            id_color = COLOR_MAP.get(en_color, "")
            if not id_color:
                continue

            img_obj = row.get("image") or {}
            img_src = img_obj.get("src") if isinstance(img_obj, dict) else None
            img_w = int(img_obj.get("width") or 0) if isinstance(img_obj, dict) else 0
            if not img_src or img_w < 300:
                continue

            candidates.append(
                {
                    "row": row,
                    "img_src": img_src,
                    "major_cat": major_cat,
                    "sub_cat_id": sub_cat_id,
                    "price_range": price_range,
                    "id_color": id_color,
                    "en_color": en_color,
                    "article_type": article_type,
                }
            )
            cat_counts[major_cat] += 1

        offset += batch_len
        print(f"  -> Menemukan {len(candidates)}/{target_total} kandidat foto HD (900x1200)...")

    return candidates


def _download_and_save_hd_image(args: tuple[int, str, Path]) -> tuple[int, bool]:
    idx_num, url, out_path = args
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width < 300:
            return idx_num, False
        # Simpan pada ukuran tajam 600x800 (rasio studio 3:4 / 4:5) kualitas tinggi 93
        if img.width > 660:
            ratio = 600 / img.width
            img = img.resize((600, int(img.height * ratio)), Image.Resampling.LANCZOS)
        img.save(out_path, format="JPEG", quality=93, optimize=True)
        img.close()
        return idx_num, True
    except Exception:
        return idx_num, False


def seed_catalog(target_total: int = 240, force_refresh: bool = False) -> None:
    init_db()
    PRODUCTS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh:
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        sample_hd = list(PRODUCTS_IMG_DIR.glob("hd_prod_*.jpg"))
        if existing >= target_total and len(sample_hd) >= target_total - 10:
            print(f"Database sudah memiliki {existing} produk HD. Melewati unduhan ulang.")
            return

    # Hapus foto thumbnail lama (prod_*.jpg) agar tidak menyisakan gambar buram
    for old_file in PRODUCTS_IMG_DIR.glob("prod_*.jpg"):
        try:
            old_file.unlink()
        except OSError:
            pass
    for old_hd in PRODUCTS_IMG_DIR.glob("hd_prod_*.jpg"):
        try:
            old_hd.unlink()
        except OSError:
            pass

    with get_connection() as conn:
        conn.execute("DELETE FROM products")
        conn.commit()

    print("Mengambil daftar foto studio resolusi tinggi (900x1200 px) dari Hugging Face...")
    candidates = fetch_hd_candidates_via_api(target_total=target_total)

    download_tasks = []
    for i, cand in enumerate(candidates, start=1):
        fname = f"hd_prod_{i:04d}.jpg"
        cand["image_filename"] = fname
        download_tasks.append((i, cand["img_src"], PRODUCTS_IMG_DIR / fname))

    print(f"Mengunduh paralel {len(download_tasks)} foto produk HD...")
    ok_indices: set[int] = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for idx_num, ok in pool.map(_download_and_save_hd_image, download_tasks):
            if ok:
                ok_indices.add(idx_num)

    rng = random.Random(2026)
    inserted_products: list[dict[str, Any]] = []

    for i, cand in enumerate(candidates, start=1):
        if i not in ok_indices:
            continue
        row = cand["row"]
        major_cat = cand["major_cat"]
        sub_cat_id = cand["sub_cat_id"]
        price_range = cand["price_range"]
        id_color = cand["id_color"]
        en_color = cand["en_color"]
        article_type = cand["article_type"]

        en_gender = str(row.get("gender") or "Unisex").strip()
        id_gender = GENDER_MAP.get(en_gender, "Unisex")
        en_usage = str(row.get("usage") or "Casual").strip()
        id_usage = USAGE_MAP.get(en_usage, "Kasual")
        en_display = str(
            row.get("productDisplayName") or f"{en_gender} {en_color} {article_type}"
        ).strip()

        pattern_id = detect_visual_pattern_id(en_display)
        series_tag = rng.choice(SERIES_LABELS)
        sku = f"KLA-{1000 + i}"

        if i % 3 != 0:
            store_name = f"{sub_cat_id} {id_gender} {series_tag} #{100 + i}"
            store_desc = (
                f"Koleksi {sub_cat_id.lower()} {id_gender.lower()} bergaya {id_usage.lower()} "
                f"dari KALA Studio. Nyaman digunakan untuk aktivitas harian dengan potongan rapi."
            )
        else:
            store_name = f"{sub_cat_id} {id_gender} {id_color} {series_tag}"
            store_desc = (
                f"{sub_cat_id} warna {id_color.lower()} untuk {id_gender.lower()} "
                f"cocok dipakai suasana {id_usage.lower()}."
            )

        visual_parts = [sub_cat_id.lower(), id_gender.lower(), f"warna {id_color.lower()}"]
        if pattern_id:
            visual_parts.append(pattern_id)
        if id_usage.lower() in ("olahraga", "formal"):
            visual_parts.append(id_usage.lower())
        visual_query_id = " ".join(visual_parts)

        price = rng.randrange(price_range[0], price_range[1], 10000)
        stock = rng.randint(6, 35)

        saved = create_product(
            {
                "sku": sku,
                "name": store_name,
                "category": major_cat,
                "sub_category": sub_cat_id,
                "gender": id_gender,
                "color": id_color,
                "price": price,
                "stock": stock,
                "description": store_desc,
                "visual_caption_en": f"{en_display}. {en_gender} {en_color} {en_usage} {article_type}",
                "visual_query_id": visual_query_id,
                "image_filename": cand["image_filename"],
            }
        )
        inserted_products.append(saved)

    by_visual_key: dict[str, list[int]] = {}
    finetune_records: list[dict[str, Any]] = []

    for p in inserted_products:
        vq = p["visual_query_id"]
        by_visual_key.setdefault(vq, []).append(int(p["id"]))
        finetune_records.append(
            {
                "product_id": int(p["id"]),
                "query_id": vq,
                "query_en": p["visual_caption_en"],
                "image_path": f"app/static/products/{p['image_filename']}",
                "category": p["category"],
            }
        )

    eval_queries = [
        {"query": q_str, "relevant_ids": pids}
        for q_str, pids in by_visual_key.items()
    ]
    rng.shuffle(eval_queries)
    eval_queries = eval_queries[:80]

    (DATA_DIR / "eval_queries.json").write_text(
        json.dumps(eval_queries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (DATA_DIR / "finetune_pairs.jsonl").open("w", encoding="utf-8") as f:
        for rec in finetune_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(
        f"Selesai! {len(inserted_products)} foto produk HD tajam (600x800 px) tersimpan di database."
    )


if __name__ == "__main__":
    force = "--force" in sys.argv
    seed_catalog(target_total=240, force_refresh=force)
