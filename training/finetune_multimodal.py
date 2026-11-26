"""
Pipeline Domain Adaptation (Finetuning) Multimodal Embedding E-Commerce
Melatih ulang model sentence-transformers/clip-ViT-B-32 pada pasangan deskripsi visual
dan foto studio produk fashion menggunakan SentenceTransformerTrainer.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from datasets import Dataset
from PIL import Image
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
)
from sentence_transformers.losses import MultipleNegativesRankingLoss
from sentence_transformers.training_args import BatchEvalStrategy

BASE_DIR = Path(__file__).resolve().parent.parent
PAIRS_PATH = BASE_DIR / "data" / "finetune_pairs.jsonl"
OUTPUT_MODEL_DIR = BASE_DIR / "models" / "clip-ecommerce-finetuned"


def load_ecommerce_multimodal_dataset() -> tuple[Dataset, Dataset]:
    records = []
    with PAIRS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            img_path = BASE_DIR / row["image_path"]
            if img_path.exists():
                records.append(
                    {
                        "anchor": row["query_en"],
                        "positive": Image.open(img_path).convert("RGB"),
                    }
                )
    ds = Dataset.from_list(records)
    split = ds.train_test_split(test_size=0.2, seed=42)
    return split["train"], split["test"]


def compute_ndcg_at_10(model: SentenceTransformer, eval_ds: Dataset) -> float:
    queries = [row["anchor"] for row in eval_ds]
    images = [row["positive"] for row in eval_ds]

    q_embs = model.encode(queries, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)
    d_embs = model.encode(images, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)

    sims = np.matmul(q_embs, d_embs.T)
    ndcgs = []
    for i in range(len(queries)):
        ranked = np.argsort(-sims[i])[:10]
        dcg = 0.0
        for rank_idx, doc_idx in enumerate(ranked):
            if int(doc_idx) == i:
                dcg = 1.0 / math.log2(rank_idx + 2)
                break
        ndcgs.append(dcg)
    return float(np.mean(ndcgs))


def main() -> None:
    model_name = "sentence-transformers/clip-ViT-B-32"
    print(f"Memuat model multimodal: {model_name}")
    model = SentenceTransformer(model_name)

    train_ds, eval_ds = load_ecommerce_multimodal_dataset()
    print(f"Data latih: {len(train_ds)} pasang | Data uji: {len(eval_ds)} pasang")

    base_ndcg = compute_ndcg_at_10(model, eval_ds)
    print(f"Skor Awal (Base Model) NDCG@10: {base_ndcg:.4f}")

    loss = MultipleNegativesRankingLoss(model=model, scale=20.0)

    args = SentenceTransformerTrainingArguments(
        output_dir=str(BASE_DIR / "models" / "checkpoints"),
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=1e-5,
        warmup_ratio=0.1,
        fp16=torch.cuda.is_available(),
        eval_strategy=BatchEvalStrategy.STEPS,
        eval_steps=15,
        save_strategy=BatchEvalStrategy.STEPS,
        save_steps=15,
        save_total_limit=2,
        logging_steps=5,
    )

    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        loss=loss,
    )
    trainer.train()

    finetuned_ndcg = compute_ndcg_at_10(model, eval_ds)
    print(f"Skor Akhir (Finetuned Model) NDCG@10: {finetuned_ndcg:.4f}")

    OUTPUT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUTPUT_MODEL_DIR))
    print(f"Model tersimpan di: {OUTPUT_MODEL_DIR}")

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    labels = ["CLIP ViT-B/32\n(Base Model)", "CLIP ViT-B/32\n(Finetuned E-Commerce)"]
    scores = [base_ndcg, finetuned_ndcg]
    bars = ax.bar(labels, scores, color=["#64748b", "#111111"], width=0.45)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("NDCG@10")
    ax.set_title("Benchmark Multimodal Product Retrieval: Base vs Finetuned")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    for bar, sc in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            sc + 0.02,
            f"{sc:.4f}",
            ha="center",
            fontweight="bold",
        )
    chart_path = BASE_DIR / "training" / "benchmark_ndcg10.png"
    plt.tight_layout()
    plt.savefig(chart_path)
    print(f"Grafik benchmark tersimpan di: {chart_path}")


if __name__ == "__main__":
    main()
