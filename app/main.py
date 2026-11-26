"""
Backend Utama FastAPI: Sistem Informasi E-Commerce KALA Studio + Mesin Pencari Multimodal AI.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("HF_HOME", str(BASE_DIR / ".cache" / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(BASE_DIR / ".cache" / "torch"))

from ai_engine.multimodal_retriever import MODEL_PROFILES, MultimodalSearchEngine
from app.database import (
    create_order,
    create_product,
    delete_product,
    get_all_products_for_indexing,
    get_categories_summary,
    get_dashboard_stats,
    get_product_by_id,
    init_db,
    list_orders,
    list_products,
    sql_keyword_search,
    update_order_status,
)

app = FastAPI(
    title="KALA — Flagship E-Commerce & Multimodal Visual Search API",
    version="1.0.0",
)

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
PRODUCTS_IMG_DIR = STATIC_DIR / "products"
UPLOADS_DIR = STATIC_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"

PRODUCTS_IMG_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

search_engine = MultimodalSearchEngine()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    search_engine.detect_hardware()
    search_engine.load_index_from_disk()


class OrderItemInput(BaseModel):
    product_id: int
    quantity: int


class OrderCreateInput(BaseModel):
    customer_name: str
    customer_phone: str
    shipping_address: str
    payment_method: str
    items: list[OrderItemInput]


class OrderStatusInput(BaseModel):
    status: str


class SwitchModelInput(BaseModel):
    profile_id: str


@app.get("/", response_class=HTMLResponse)
async def storefront_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_and_research_page(request: Request) -> HTMLResponse:
    stats = get_dashboard_stats()
    hw = search_engine.detect_hardware()
    return templates.TemplateResponse(
        request=request,
        name="admin_research.html",
        context={
            "stats": stats,
            "hardware": hw,
            "model_profiles": list(MODEL_PROFILES.values()),
        },
    )


@app.get("/api/products")
async def api_list_products(category: str = "Semua", limit: int = 260) -> dict[str, Any]:
    items = list_products(category=category, limit=limit)
    return {
        "products": items,
        "categories": get_categories_summary(),
        "total": len(items),
    }


@app.get("/api/products/{product_id}")
async def api_get_product(product_id: int) -> dict[str, Any]:
    prod = get_product_by_id(product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    return prod


@app.post("/api/search")
async def api_multimodal_search(
    query_text: str = Form(""),
    mode: str = Form("multimodal_rerank"),
    category: str = Form("Semua"),
    top_k: int = Form(24),
    query_image: UploadFile | None = File(None),
) -> dict[str, Any]:
    """
    Endpoint pencarian terpadu yang mendukung:
    - mode="sql_keyword"       : Pencarian SQL LIKE konvensional (pembanding baseline)
    - mode="multimodal_base"   : Pencarian AI Multimodal Stage-1 (Base Embedding)
    - mode="multimodal_rerank" : Pencarian AI Multimodal Stage-2 (Embedding + Reranker)
    Input dapat berupa teks saja, gambar saja, atau gabungan gambar + teks!
    """
    clean_text = (query_text or "").strip()
    pil_img: Image.Image | None = None

    if query_image is not None and query_image.filename:
        raw_bytes = await query_image.read()
        if raw_bytes:
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

    if not clean_text and pil_img is None:
        items = list_products(category=category, limit=top_k)
        return {
            "mode": "catalog_browse",
            "modality": "browse",
            "stage": "Katalog Terbaru",
            "latency_ms": 1.0,
            "products": items,
            "notice": "",
        }

    # 1. Mode SQL Keyword Konvensional
    if mode == "sql_keyword":
        t0 = time.perf_counter()
        if pil_img is not None and not clean_text:
            return {
                "mode": "sql_keyword",
                "modality": "unsupported_image",
                "stage": "SQL Keyword Biasa (LIKE)",
                "latency_ms": 0.5,
                "products": [],
                "notice": "Pencarian database SQL konvensional tidak dapat memproses input gambar tanpa teks kata kunci.",
            }
        rows = sql_keyword_search(clean_text, category=category, limit=top_k)
        lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "mode": "sql_keyword",
            "modality": "sql_text",
            "stage": "SQL Keyword Biasa (LIKE '%kata%')",
            "latency_ms": lat_ms,
            "products": rows,
            "notice": (
                "SQL hanya mencocokkan teks literal di judul/deskripsi. Produk yang fotonya sesuai tetapi judulnya tidak memuat kata tersebut tidak akan ditemukan."
                if len(rows) < 4
                else ""
            ),
        }

    # 2. Mode AI Multimodal (Sentence Transformers)
    all_prods = get_all_products_for_indexing()
    prods_by_id = {int(p["id"]): p for p in all_prods}

    if search_engine.image_embeddings is None and not search_engine.load_index_from_disk():
        search_engine.build_product_index(all_prods, batch_size=32)

    use_reranker = mode != "multimodal_base"
    ai_out = search_engine.search(
        query_text=clean_text,
        query_image=pil_img,
        top_k=min(len(all_prods), max(top_k * 2, 48)),
        use_reranker=use_reranker,
        products_by_id=prods_by_id,
    )

    if pil_img is not None:
        pil_img.close()

    enriched: list[dict[str, Any]] = []
    for hit in ai_out["results"]:
        prod = prods_by_id.get(int(hit["product_id"]))
        if not prod:
            continue
        if category and category != "Semua" and prod["category"] != category:
            continue
        item_copy = dict(prod)
        item_copy["rank"] = len(enriched) + 1
        item_copy["score"] = hit["score"]
        item_copy["visual_cosine"] = hit["visual_cosine"]
        item_copy["similarity_pct"] = hit["similarity_pct"]
        enriched.append(item_copy)
        if len(enriched) >= top_k:
            break

    return {
        "mode": mode,
        "modality": ai_out["modality"],
        "stage": ai_out["stage"],
        "profile": ai_out.get("profile", ""),
        "latency_ms": ai_out["latency_ms"],
        "products": enriched,
        "notice": "",
    }


@app.post("/api/admin/products")
async def api_admin_create_product(
    name: str = Form(...),
    category: str = Form(...),
    sub_category: str = Form(""),
    gender: str = Form("Unisex"),
    color: str = Form("Netral"),
    price: int = Form(...),
    stock: int = Form(15),
    description: str = Form(""),
    photo: UploadFile = File(...),
) -> dict[str, Any]:
    if not photo.filename:
        raise HTTPException(status_code=400, detail="Foto produk wajib diunggah.")

    raw = await photo.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"File gambar tidak valid: {exc}") from exc

    fname = f"custom_{uuid.uuid4().hex[:10]}.jpg"
    save_path = PRODUCTS_IMG_DIR / fname
    img.save(save_path, format="JPEG", quality=92)
    img.close()

    sub_cat_clean = sub_category.strip() or category
    visual_q = f"{sub_cat_clean.lower()} {gender.lower()} warna {color.lower()}"
    prod = create_product(
        {
            "name": name.strip(),
            "category": category.strip(),
            "sub_category": sub_cat_clean,
            "gender": gender.strip(),
            "color": color.strip(),
            "price": price,
            "stock": stock,
            "description": description.strip(),
            "visual_caption_en": f"{name} {sub_cat_clean} {color} {gender}",
            "visual_query_id": visual_q,
            "image_filename": fname,
        }
    )

    # Otomatis tambahkan foto baru ke indeks vektor GPU secara real-time!
    search_engine.add_single_product_to_index(prod)
    return {"message": "Produk berhasil disimpan dan diindeks ke AI Multimodal.", "product": prod}


@app.delete("/api/admin/products/{product_id}")
async def api_admin_delete_product(product_id: int) -> dict[str, Any]:
    prod = get_product_by_id(product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    ok = delete_product(product_id)
    return {"deleted": ok, "product_id": product_id}


@app.post("/api/orders")
async def api_create_order(payload: OrderCreateInput) -> dict[str, Any]:
    if not payload.items:
        raise HTTPException(status_code=400, detail="Keranjang belanja masih kosong.")
    try:
        order = create_order(
            customer_name=payload.customer_name.strip(),
            customer_phone=payload.customer_phone.strip(),
            shipping_address=payload.shipping_address.strip(),
            payment_method=payload.payment_method.strip(),
            items=[item.model_dump() for item in payload.items],
        )
        return {"message": "Pesanan berhasil dibuat!", "order": order}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/orders")
async def api_list_orders() -> dict[str, Any]:
    return {"orders": list_orders(limit=50), "stats": get_dashboard_stats()}


@app.patch("/api/orders/{order_id}/status")
async def api_update_order_status(order_id: int, payload: OrderStatusInput) -> dict[str, Any]:
    ok = update_order_status(order_id, payload.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
    return {"updated": True, "status": payload.status}


@app.get("/api/research/status")
async def api_research_status() -> dict[str, Any]:
    hw = search_engine.detect_hardware()
    eval_cache_path = DATA_DIR / "latest_benchmark.json"
    cached_eval = None
    if eval_cache_path.exists():
        cached_eval = json.loads(eval_cache_path.read_text(encoding="utf-8"))
    return {
        "hardware": hw,
        "profiles": list(MODEL_PROFILES.values()),
        "stats": get_dashboard_stats(),
        "latest_benchmark": cached_eval,
    }


@app.post("/api/research/evaluate")
async def api_run_evaluation() -> dict[str, Any]:
    eval_file = DATA_DIR / "eval_queries.json"
    if not eval_file.exists():
        raise HTTPException(
            status_code=400,
            detail="File data/eval_queries.json belum tersedia. Jalankan seeder produk terlebih dahulu.",
        )
    eval_queries = json.loads(eval_file.read_text(encoding="utf-8"))
    all_prods = get_all_products_for_indexing()
    prods_by_id = {int(p["id"]): p for p in all_prods}

    if search_engine.image_embeddings is None and not search_engine.load_index_from_disk():
        search_engine.build_product_index(all_prods, batch_size=32)

    report = search_engine.evaluate_benchmark(
        eval_queries=eval_queries,
        sql_search_fn=sql_keyword_search,
        products_by_id=prods_by_id,
        k=10,
    )
    (DATA_DIR / "latest_benchmark.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


@app.post("/api/research/reindex")
async def api_rebuild_index() -> dict[str, Any]:
    all_prods = get_all_products_for_indexing()
    res = search_engine.build_product_index(all_prods, batch_size=32)
    return res


@app.post("/api/research/switch-model")
async def api_switch_model(payload: SwitchModelInput) -> dict[str, Any]:
    if payload.profile_id not in MODEL_PROFILES:
        raise HTTPException(status_code=400, detail="Profil model tidak dikenali.")
    global search_engine
    candidate = MultimodalSearchEngine(profile_id=payload.profile_id)
    try:
        candidate.load_model()
        if not candidate.load_index_from_disk():
            all_prods = get_all_products_for_indexing()
            candidate.build_product_index(all_prods, batch_size=16)
        search_engine = candidate
        return {
            "switched": True,
            "active_profile": search_engine.profile,
            "indexed_count": len(search_engine.product_ids),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
