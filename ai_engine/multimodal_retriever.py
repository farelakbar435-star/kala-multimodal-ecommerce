"""
Modul Pencarian Produk Multimodal & Cross-Modal Reranker berbasis Sentence Transformers.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache" / "huggingface"
os.environ.setdefault("HF_HOME", str(CACHE_DIR))
os.environ.setdefault("TORCH_HOME", str(BASE_DIR / ".cache" / "torch"))

DATA_DIR = BASE_DIR / "data"
PRODUCTS_IMG_DIR = BASE_DIR / "app" / "static" / "products"

MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "clip-fast": {
        "id": "clip-fast",
        "label": "CLIP ViT-B/32 Multimodal (Base Model)",
        "hf_name": "sentence-transformers/clip-ViT-B-32",
        "architecture": "clip",
        "vram_estimate": "~1.2 GB VRAM",
        "description": "Model multimodal Sentence Transformers untuk pencarian visual dan teks secara real-time.",
    },
    "clip-finetuned": {
        "id": "clip-finetuned",
        "label": "CLIP ViT-B/32 Multimodal (Finetuned E-Commerce)",
        "hf_name": str(BASE_DIR / "models" / "clip-ecommerce-finetuned"),
        "architecture": "clip",
        "vram_estimate": "~1.2 GB VRAM",
        "description": "Model CLIP ViT-B/32 yang telah di-finetune pada katalog produk fashion menggunakan SentenceTransformerTrainer.",
    },
}

# Kamus jembatan atribut visual Bahasa Indonesia -> Bahasa Inggris
# Membantu model berbasis CLIP memahami deskripsi visual Bahasa Indonesia secara presisi.
ID_TO_EN_FASHION_TERMS: list[tuple[str, str]] = [
    ("lengan panjang", "long sleeve"),
    ("lengan pendek", "short sleeve"),
    ("tanpa lengan", "sleeveless"),
    ("kotak-kotak", "checkered plaid"),
    ("kotak", "checkered plaid"),
    ("garis-garis", "striped"),
    ("garis", "striped"),
    ("polos", "solid plain"),
    ("bermotif", "patterned printed"),
    ("motif bunga", "floral print"),
    ("biru dongker", "navy blue"),
    ("biru muda", "light blue"),
    ("biru tua", "dark blue"),
    ("merah muda", "pink"),
    ("merah marun", "maroon burgundy"),
    ("abu-abu", "grey charcoal"),
    ("coklat tua", "dark brown"),
    ("coklat", "brown"),
    ("hijau zaitun", "olive green"),
    ("hijau", "green"),
    ("kuning", "yellow"),
    ("ungu", "purple"),
    ("putih", "white"),
    ("hitam", "black"),
    ("merah", "red"),
    ("biru", "blue"),
    ("krem", "beige cream"),
    ("emas", "gold metallic"),
    ("perak", "silver metallic"),
    ("kemeja", "button-down shirt"),
    ("kaos polo", "polo collar t-shirt"),
    ("kaos", "t-shirt top"),
    ("jaket", "jacket outerwear"),
    ("sweater", "sweater pullover hoodie"),
    ("hoodie", "hooded sweatshirt"),
    ("celana pendek", "shorts"),
    ("celana panjang", "trousers pants"),
    ("celana jeans", "denim jeans"),
    ("celana", "pants trousers"),
    ("rok", "skirt"),
    ("gaun", "dress gown"),
    ("sepatu olahraga", "sports running sneakers shoes"),
    ("sepatu lari", "running athletic sneakers"),
    ("sepatu formal", "formal leather dress shoes"),
    ("sepatu kasual", "casual sneakers shoes"),
    ("sepatu", "shoes footwear"),
    ("sandal", "sandals flip-flops"),
    ("tas ransel", "backpack bag"),
    ("tas tangan", "handbag purse tote"),
    ("tas selempang", "sling shoulder bag"),
    ("dompet", "wallet clutch"),
    ("tas", "bag"),
    ("jam tangan", "wristwatch analog digital watch"),
    ("kacamata", "sunglasses eyewear"),
    ("ikat pinggang", "leather belt"),
    ("pria", "men male"),
    ("wanita", "women female"),
    ("anak", "kids"),
    ("olahraga", "sporty athletic"),
    ("resmi", "formal office"),
    ("formal", "formal office"),
    ("kasual", "casual everyday"),
    ("santai", "casual relaxed"),
    ("kulit", "leather"),
    ("kanvas", "canvas"),
    ("denim", "denim"),
]


def translate_fashion_query_for_clip(query_id: str) -> str:
    """Menerjemahkan istilah visual pakaian Bahasa Indonesia ke deskripsi visual CLIP."""
    text = query_id.lower().strip()
    # Hapus kata pengantar pencarian seperti "cari model seperti ini tapi..."
    filler_patterns = [
        r"\bcari\b",
        r"\bcarikan\b",
        r"\byang\b",
        r"\bseperti\b",
        r"\bini\b",
        r"\bfoto\b",
        r"\bgambar\b",
        r"\btapi\b",
        r"\bnamun\b",
        r"\bdengan\b",
        r"\bwarna\b",
        r"\bmodel\b",
        r"\bproduk\b",
        r"\bbarang\b",
    ]
    cleaned = text
    for pat in filler_patterns:
        cleaned = re.sub(pat, " ", cleaned)

    result = cleaned
    for id_term, en_term in ID_TO_EN_FASHION_TERMS:
        result = re.sub(rf"\b{re.escape(id_term)}\b", en_term, result)
    result = re.sub(r"\s+", " ", result).strip()
    return f"a studio product photo of {result}" if result else query_id


def _l2_normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=-1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (vecs / norms).astype(np.float32)


class MultimodalSearchEngine:
    """
    Mesin pencari produk multimodal berbasis Sentence Transformers.
    Mendukung:
    1. Teks -> Gambar Produk (Text-to-Image Retrieval)
    2. Gambar -> Gambar Produk (Visual Similarity Search)
    3. Gambar + Teks -> Gambar Produk (Composed Multimodal Retrieval)
    4. Tahap ke-2 Cross-Modal Reranking & Evaluasi Benchmark (NDCG@10)
    """

    def __init__(self, profile_id: str | None = None) -> None:
        env_profile = os.getenv("ACTIVE_MODEL_PROFILE", "clip-fast").strip()
        self.profile_id = profile_id or env_profile
        if self.profile_id not in MODEL_PROFILES:
            self.profile_id = "clip-fast"

        self.model: Any = None
        self.reranker: Any = None
        self.device: str = "cpu"
        self.gpu_name: str = "CPU"

        # Cache matriks embedding di RAM untuk pencarian < 20ms
        self.product_ids: list[int] = []
        self.image_embeddings: np.ndarray | None = None
        self.text_embeddings: np.ndarray | None = None

    @property
    def profile(self) -> dict[str, Any]:
        return MODEL_PROFILES[self.profile_id]

    @property
    def index_dir(self) -> Path:
        d = DATA_DIR / "indices" / self.profile_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def detect_hardware(self) -> dict[str, Any]:
        import torch

        if torch.cuda.is_available():
            self.device = "cuda"
            self.gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        else:
            self.device = "cpu"
            self.gpu_name = "CPU"
            vram_gb = 0.0
        return {
            "device": self.device,
            "gpu_name": self.gpu_name,
            "vram_gb": vram_gb,
            "active_profile": self.profile,
            "index_ready": (self.index_dir / "image_embeddings.npy").exists(),
            "indexed_count": len(self.product_ids),
        }

    def load_model(self) -> None:
        if self.model is not None:
            return

        from sentence_transformers import SentenceTransformer

        self.detect_hardware()
        hf_target = self.profile["hf_name"]

        if self.profile_id == "clip-finetuned" and not Path(hf_target).exists():
            raise FileNotFoundError(
                f"Folder model hasil finetune belum ditemukan di: {hf_target}. "
                "Jalankan script training/finetune_multimodal.py terlebih dahulu atau gunakan profil clip-fast."
            )
        self.model = SentenceTransformer(hf_target, device=self.device)

    def load_index_from_disk(self) -> bool:
        img_path = self.index_dir / "image_embeddings.npy"
        txt_path = self.index_dir / "text_embeddings.npy"
        ids_path = self.index_dir / "product_ids.json"

        if img_path.exists() and ids_path.exists():
            self.image_embeddings = np.load(img_path)
            self.text_embeddings = np.load(txt_path) if txt_path.exists() else self.image_embeddings
            self.product_ids = json.loads(ids_path.read_text(encoding="utf-8"))
            return True
        return False

    def build_product_index(self, products: list[dict[str, Any]], batch_size: int = 16) -> dict[str, Any]:
        """Menghitung dan menyimpan vektor embedding untuk seluruh foto & metadata produk."""
        t0 = time.perf_counter()
        self.load_model()

        valid_ids: list[int] = []
        pil_images: list[Image.Image] = []
        rich_texts: list[str] = []

        for p in products:
            img_file = PRODUCTS_IMG_DIR / p["image_filename"]
            if not img_file.exists():
                continue
            img = Image.open(img_file).convert("RGB")
            pil_images.append(img)
            valid_ids.append(int(p["id"]))
            caption = p.get("visual_caption_en") or p.get("name", "")
            rich_texts.append(
                f"{p.get('name', '')}. {p.get('sub_category', '')} {p.get('color', '')} {p.get('gender', '')}. {caption}"
            )

        if not valid_ids:
            return {"indexed": 0, "elapsed_sec": 0.0}

        img_embs = self.model.encode(
            pil_images,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        txt_embs = self.model.encode(
            rich_texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        for img in pil_images:
            img.close()

        self.image_embeddings = _l2_normalize(np.asarray(img_embs, dtype=np.float32))
        self.text_embeddings = _l2_normalize(np.asarray(txt_embs, dtype=np.float32))
        self.product_ids = valid_ids

        np.save(self.index_dir / "image_embeddings.npy", self.image_embeddings)
        np.save(self.index_dir / "text_embeddings.npy", self.text_embeddings)
        (self.index_dir / "product_ids.json").write_text(
            json.dumps(self.product_ids), encoding="utf-8"
        )

        elapsed = round(time.perf_counter() - t0, 2)
        return {
            "indexed": len(self.product_ids),
            "elapsed_sec": elapsed,
            "device": self.device,
            "gpu_name": self.gpu_name,
            "profile": self.profile_id,
        }

    def add_single_product_to_index(self, product: dict[str, Any]) -> None:
        """Mengindeks 1 produk baru secara instan saat Admin menambah barang lewat form CRUD."""
        self.load_model()
        if self.image_embeddings is None:
            self.load_index_from_disk()

        img_file = PRODUCTS_IMG_DIR / product["image_filename"]
        if not img_file.exists():
            return

        with Image.open(img_file) as raw_img:
            img = raw_img.convert("RGB")
            caption = translate_fashion_query_for_clip(
                f"{product.get('name', '')} {product.get('sub_category', '')} {product.get('color', '')} {product.get('description', '')}"
            )
            img_emb = self.model.encode(
                [img], convert_to_numpy=True, normalize_embeddings=True
            )
            txt_emb = self.model.encode(
                [caption], convert_to_numpy=True, normalize_embeddings=True
            )

        img_emb = _l2_normalize(np.asarray(img_emb, dtype=np.float32))
        txt_emb = _l2_normalize(np.asarray(txt_emb, dtype=np.float32))
        pid = int(product["id"])

        if self.image_embeddings is None or len(self.product_ids) == 0:
            self.image_embeddings = img_emb
            self.text_embeddings = txt_emb
            self.product_ids = [pid]
        else:
            if pid in self.product_ids:
                idx = self.product_ids.index(pid)
                self.image_embeddings[idx] = img_emb[0]
                if self.text_embeddings is not None:
                    self.text_embeddings[idx] = txt_emb[0]
            else:
                self.image_embeddings = np.vstack([self.image_embeddings, img_emb])
                self.text_embeddings = (
                    np.vstack([self.text_embeddings, txt_emb])
                    if self.text_embeddings is not None
                    else self.image_embeddings
                )
                self.product_ids.append(pid)

        np.save(self.index_dir / "image_embeddings.npy", self.image_embeddings)
        if self.text_embeddings is not None:
            np.save(self.index_dir / "text_embeddings.npy", self.text_embeddings)
        (self.index_dir / "product_ids.json").write_text(
            json.dumps(self.product_ids), encoding="utf-8"
        )

    def encode_multimodal_query(
        self,
        query_text: str = "",
        query_image: Image.Image | None = None,
    ) -> tuple[np.ndarray, str]:
        """
        Mengubah input pencarian (Teks saja, Foto saja, atau Foto + Teks) menjadi satu vektor query.
        """
        self.load_model()
        clean_text = (query_text or "").strip()

        # Arsitektur CLIP Multimodal
        en_prompt = translate_fashion_query_for_clip(clean_text) if clean_text else ""
        if query_image is not None and clean_text:
            img_vec = self.model.encode(
                [query_image], convert_to_numpy=True, normalize_embeddings=True
            )[0]
            txt_vec = self.model.encode(
                [en_prompt], convert_to_numpy=True, normalize_embeddings=True
            )[0]
            # Composed Image Retrieval: mempertahankan struktur bentuk dari foto + menggeser atribut warna/gaya lewat teks
            composed = 0.45 * img_vec + 0.55 * txt_vec
            return _l2_normalize(composed)[0 if composed.ndim > 1 else slice(None)], "multimodal_image_text"
        elif query_image is not None:
            img_vec = self.model.encode(
                [query_image], convert_to_numpy=True, normalize_embeddings=True
            )[0]
            return _l2_normalize(img_vec), "image_only"
        else:
            txt_vec = self.model.encode(
                [en_prompt], convert_to_numpy=True, normalize_embeddings=True
            )[0]
            return _l2_normalize(txt_vec), "text_only"

    def search(
        self,
        query_text: str = "",
        query_image: Image.Image | None = None,
        top_k: int = 24,
        use_reranker: bool = True,
        products_by_id: dict[int, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Menjalankan pencarian 2-tahap:
        Tahap 1: Dense Multimodal Retrieval (Cosine Similarity terhadap foto produk)
        Tahap 2: Cross-Modal Reranking (menggabungkan sinyal visual foto + representasi semantik atribut produk)
        """
        t0 = time.perf_counter()
        if self.image_embeddings is None and not self.load_index_from_disk():
            return {"results": [], "latency_ms": 0.0, "modality": "unindexed"}

        assert self.image_embeddings is not None
        q_vec, modality_used = self.encode_multimodal_query(query_text, query_image)

        # Tahap 1: Skor kemiripan langsung terhadap piksel foto produk (Pure Visual Embedding)
        visual_scores = np.dot(self.image_embeddings, q_vec)

        if not use_reranker or self.text_embeddings is None:
            final_scores = visual_scores
            stage_label = "Stage-1 Base Multimodal Embedding"
        else:
            # Tahap 2: Reranking pada kandidat teratas dengan menyelaraskan embedding visual & teks multimodal
            candidate_k = min(len(self.product_ids), max(top_k * 3, 60))
            top_cand_idx = np.argsort(-visual_scores)[:candidate_k]

            final_scores = np.full_like(visual_scores, -1.0)
            semantic_scores = np.dot(self.text_embeddings[top_cand_idx], q_vec)

            # Bonus keselarasan atribut eksplisit untuk reranker lintas-modal
            lexical_bonus = np.zeros(len(top_cand_idx), dtype=np.float32)
            if products_by_id and query_text.strip():
                q_tokens = [
                    tok for tok in re.split(r"\W+", query_text.lower()) if len(tok) >= 3
                ]
                for i, idx in enumerate(top_cand_idx):
                    pid = self.product_ids[int(idx)]
                    prod = products_by_id.get(pid)
                    if prod and q_tokens:
                        haystack = (
                            f"{prod.get('sub_category', '')} {prod.get('color', '')} "
                            f"{prod.get('gender', '')} {prod.get('description', '')}"
                        ).lower()
                        hits = sum(1 for tok in q_tokens if tok in haystack)
                        lexical_bonus[i] = 0.06 * (hits / len(q_tokens))

            if modality_used == "image_only":
                reranked = 0.85 * visual_scores[top_cand_idx] + 0.15 * semantic_scores
            elif modality_used == "multimodal_image_text":
                reranked = (
                    0.55 * visual_scores[top_cand_idx]
                    + 0.45 * semantic_scores
                    + lexical_bonus
                )
            else:
                reranked = (
                    0.62 * visual_scores[top_cand_idx]
                    + 0.38 * semantic_scores
                    + lexical_bonus
                )

            final_scores[top_cand_idx] = reranked
            stage_label = "Stage-2 Multimodal Embedding + Reranker"

        ranked_indices = np.argsort(-final_scores)[:top_k]
        # Kalibrasi skor kosinus CLIP (~0.18-0.36) ke persentase tampilan intuitif
        is_clip = self.profile["architecture"] == "clip"

        results: list[dict[str, Any]] = []
        for rank_pos, idx in enumerate(ranked_indices, start=1):
            raw_score = float(final_scores[int(idx)])
            vis_score = float(visual_scores[int(idx)])
            if is_clip:
                # Pemetaan sigmoid terkalibrasi khusus rentang logit/cosine CLIP ViT-B/32
                display_pct = round(
                    100.0 / (1.0 + math.exp(-18.0 * (raw_score - 0.21))), 1
                )
            else:
                display_pct = round(max(0.0, min(99.9, raw_score * 100.0)), 1)

            results.append(
                {
                    "rank": rank_pos,
                    "product_id": self.product_ids[int(idx)],
                    "score": round(raw_score, 4),
                    "visual_cosine": round(vis_score, 4),
                    "similarity_pct": display_pct,
                }
            )

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {
            "results": results,
            "latency_ms": latency_ms,
            "modality": modality_used,
            "stage": stage_label,
            "profile": self.profile["label"],
        }

    def evaluate_benchmark(
        self,
        eval_queries: list[dict[str, Any]],
        sql_search_fn: Any,
        products_by_id: dict[int, dict[str, Any]],
        k: int = 10,
    ) -> dict[str, Any]:
        """
        Menghitung metrik kualitas temu kembali informasi (NDCG@10, MRR@10, Recall@10) yang membandingkan:
        1. Pencarian SQL Keyword Biasa (LIKE)
        2. Multimodal Embedding (Stage-1 Visual Only / Base)
        3. Multimodal Embedding + Reranker (Stage-2 Hybrid)
        """

        def compute_ir_metrics(
            predicted_ids: list[int], relevant_ids: set[int]
        ) -> tuple[float, float, float]:
            top_preds = predicted_ids[:k]
            dcg = 0.0
            rr = 0.0
            hits = 0
            for i, pid in enumerate(top_preds):
                if pid in relevant_ids:
                    hits += 1
                    dcg += 1.0 / math.log2(i + 2)
                    if rr == 0.0:
                        rr = 1.0 / (i + 1)
            ideal_hits = min(len(relevant_ids), k)
            idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
            ndcg = (dcg / idcg) if idcg > 0 else 0.0
            recall = (hits / len(relevant_ids)) if relevant_ids else 0.0
            return ndcg, rr, recall

        metrics = {
            "sql_keyword": {"ndcg": [], "mrr": [], "recall": [], "latencies": []},
            "multimodal_base": {"ndcg": [], "mrr": [], "recall": [], "latencies": []},
            "multimodal_reranked": {"ndcg": [], "mrr": [], "recall": [], "latencies": []},
        }

        sample_cases: list[dict[str, Any]] = []

        for item in eval_queries:
            q_text = item["query"]
            rel_ids = set(int(x) for x in item["relevant_ids"])

            # 1. SQL Keyword
            t_sql = time.perf_counter()
            sql_rows = sql_search_fn(q_text, limit=k)
            lat_sql = (time.perf_counter() - t_sql) * 1000.0
            sql_ids = [int(r["id"]) for r in sql_rows]
            n1, m1, r1 = compute_ir_metrics(sql_ids, rel_ids)
            metrics["sql_keyword"]["ndcg"].append(n1)
            metrics["sql_keyword"]["mrr"].append(m1)
            metrics["sql_keyword"]["recall"].append(r1)
            metrics["sql_keyword"]["latencies"].append(lat_sql)

            # 2. Base Multimodal (Stage-1 Pure Visual)
            res_base = self.search(
                query_text=q_text, top_k=k, use_reranker=False, products_by_id=products_by_id
            )
            base_ids = [int(r["product_id"]) for r in res_base["results"]]
            n2, m2, r2 = compute_ir_metrics(base_ids, rel_ids)
            metrics["multimodal_base"]["ndcg"].append(n2)
            metrics["multimodal_base"]["mrr"].append(m2)
            metrics["multimodal_base"]["recall"].append(r2)
            metrics["multimodal_base"]["latencies"].append(res_base["latency_ms"])

            # 3. Multimodal + Reranker (Stage-2)
            res_rerank = self.search(
                query_text=q_text, top_k=k, use_reranker=True, products_by_id=products_by_id
            )
            rerank_ids = [int(r["product_id"]) for r in res_rerank["results"]]
            n3, m3, r3 = compute_ir_metrics(rerank_ids, rel_ids)
            metrics["multimodal_reranked"]["ndcg"].append(n3)
            metrics["multimodal_reranked"]["mrr"].append(m3)
            metrics["multimodal_reranked"]["recall"].append(r3)
            metrics["multimodal_reranked"]["latencies"].append(res_rerank["latency_ms"])

            if len(sample_cases) < 6 and n3 > n1:
                target_prod = products_by_id.get(next(iter(rel_ids)), {})
                sample_cases.append(
                    {
                        "query": q_text,
                        "target_name": target_prod.get("name", ""),
                        "target_image": target_prod.get("image_filename", ""),
                        "sql_ndcg": round(n1, 3),
                        "base_ndcg": round(n2, 3),
                        "rerank_ndcg": round(n3, 3),
                    }
                )

        summary = {}
        for key, vals in metrics.items():
            summary[key] = {
                f"ndcg@{k}": round(float(np.mean(vals["ndcg"])), 4) if vals["ndcg"] else 0.0,
                f"mrr@{k}": round(float(np.mean(vals["mrr"])), 4) if vals["mrr"] else 0.0,
                f"recall@{k}": round(float(np.mean(vals["recall"])), 4) if vals["recall"] else 0.0,
                "avg_latency_ms": round(float(np.mean(vals["latencies"])), 1)
                if vals["latencies"]
                else 0.0,
            }

        return {
            "num_queries": len(eval_queries),
            "corpus_size": len(self.product_ids),
            "k": k,
            "active_model": self.profile["label"],
            "device": f"{self.gpu_name} ({self.device.upper()})",
            "summary": summary,
            "sample_wins": sample_cases,
        }
