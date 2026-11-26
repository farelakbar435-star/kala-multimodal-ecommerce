# KALA — Flagship Fashion E-Commerce & Multimodal Visual Search

**KALA** adalah aplikasi web *e-commerce* pakaian bergaya *Japanese Architectural Retail* yang dilengkapi mesin **Pencarian Produk Multimodal (Teks, Foto, & Gabungan Foto + Teks)** serta **Cross-Modal Reranker** berbasis `Sentence Transformers` (`CLIP ViT-B/32`).

---

## Fitur Utama

### 1. Pengalaman Belanja Ritel Modern (`/`)
- **Desain Flagship Minimalis:** Antarmuka bersih berfokus pada fotografi produk studio HD (`600x800` px) dengan *color swatches*, pilihan ukuran (`XS–XXL` / `38–44`), *wishlist*, keranjang *slide-over*, dan *checkout* ber-invoice (`INV-...`).
- **Interaksi & Animasi Modern:**
  - **Lenis Smooth Scroll** yang tersinkronisasi dengan `gsap.ticker`.
  - **GSAP + ScrollTrigger** untuk animasi tipografi judul per kata (*masked word-by-word reveal*) dan efek *parallax* *hero banner*.
  - **Motion (`motion.dev` v12)** untuk animasi masuk kartu (`inView`) dan interaksi *spring hover* taktil.

### 2. Mesin Pencari AI Multimodal (`Sentence Transformers`)
- **Teks ke Visual Produk:** Menemukan pakaian berdasarkan ciri fisik pada gambar meskipun atribut warna/motif tidak tertulis secara eksplisit pada judul database.
- **Pencarian Kamera / Foto (*Visual Search*):** Unggah foto referensi atau klik tombol **Serupa** pada kartu produk untuk mencari potongan pakaian sejenis.
- **Gabungan Foto + Modifikasi Teks (*Composed Multimodal Retrieval*):** Unggah foto pakaian lalu ketik penyesuaian detail (misal: *"warna hitam"* atau *"biru dongker"*).

### 3. Portal Admin & Telemetri Pencarian (`/admin`)
- **Manajemen Toko (CRUD & Pesanan):** Tambah produk beserta unggah foto baru (otomatis diindeks ke ruang vektor GPU secara *real-time*) dan kelola status pesanan pelanggan.
- **Benchmark Mesin Pencari (`NDCG@10`, `MRR@10`, `Recall@10`):** Membandingkan performa pencarian konvensional `SQL LIKE` terhadap *Stage-1 Base Multimodal Embedding* dan *Stage-2 Multimodal + Reranker*.
- **Pipeline Finetuning:** Tersedia di `training/Finetune_Multimodal_Search.ipynb` dan `training/finetune_multimodal.py` untuk mengadaptasi model `sentence-transformers/clip-ViT-B-32` pada katalog kustom menggunakan `SentenceTransformerTrainer`.

---

## Hasil Benchmark Pencarian (240 Produk HD, 80 Kueri Visual)

| Metode Pencarian | NDCG@10 | MRR@10 | Recall@10 |
| :--- | :---: | :---: | :---: |
| SQL Keyword Konvensional (`LIKE`) | `0.2888` | `0.3688` | `0.2675` |
| Stage-1 Base Multimodal Embedding (`CLIP ViT-B/32`) | `0.7271` | `0.6730` | `0.9406` |
| **Stage-2 Multimodal Embedding + Reranker** | **`0.9309`** | **`0.9146`** | **`1.0000`** |

---

## Struktur Direktori

```text
├── ai_engine/
│   └── multimodal_retriever.py   # Engine SentenceTransformer (CLIP ViT-B/32) & Cross-Modal Reranker
├── app/
│   ├── database.py               # Modul SQLite (Produk, Transaksi Pesanan, SQL Baseline)
│   ├── main.py                   # Backend FastAPI & REST Endpoints
│   ├── static/                   # Aset JS (GSAP/Motion/Lenis), Hero Banner, & 240 Foto HD
│   └── templates/                # Tampilan Flagship Storefront (/) & Portal Admin (/admin)
├── data/                         # Database awal (kala_store.db) & data benchmark
├── scripts/
│   ├── seed_products.py          # Pengunduh otomatis katalog & foto studio HD dari Hugging Face
│   └── build_index.py            # Pembuat indeks vektor embedding di GPU/CPU
├── training/
│   ├── finetune_multimodal.py    # Script finetuning CLIP ViT-B/32 dengan SentenceTransformerTrainer
│   └── Finetune_Multimodal_Search.ipynb
├── requirements.txt
└── start.bat                     # Launcher otomatis Windows
```

---

## Cara Menjalankan Proyek

### Opsi Cepat (Windows)
Klik dua kali **`start.bat`**, atau jalankan lewat terminal:
```powershell
.\start.bat
```

### Instalasi Manual (Cross-Platform)
```bash
python -m venv .venv
# Aktifkan venv (.venv\Scripts\activate di Windows atau source .venv/bin/activate di Linux/macOS)
pip install -r requirements.txt
python scripts/build_index.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- **Halaman Toko:** `http://localhost:8000`
- **Portal Admin & Benchmark:** `http://localhost:8000/admin`
