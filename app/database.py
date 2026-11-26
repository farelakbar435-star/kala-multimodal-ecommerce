"""
Modul Database SQLite untuk Platform E-Commerce KALA.
Mencakup manajemen Produk (CRUD), Keranjang/Transaksi Pesanan, dan Pencarian SQL Konvensional.
"""

from __future__ import annotations

import datetime as dt
import random
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "kala_store.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT 'Unisex',
                color TEXT NOT NULL DEFAULT 'Netral',
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 15,
                description TEXT NOT NULL DEFAULT '',
                visual_caption_en TEXT NOT NULL DEFAULT '',
                visual_query_id TEXT NOT NULL DEFAULT '',
                image_filename TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                shipping_address TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                total_amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Menunggu Konfirmasi',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()


def list_products(category: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if category and category != "Semua":
            rows = conn.execute(
                "SELECT * FROM products WHERE category = ? ORDER BY id DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_all_products_for_indexing() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def get_product_by_id(product_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None


def get_categories_summary() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, COUNT(*) as count
            FROM products
            GROUP BY category
            ORDER BY count DESC
            """
        ).fetchall()
        total = sum(int(r["count"]) for r in rows)
        result = [{"category": "Semua", "count": total}]
        result.extend({"category": r["category"], "count": int(r["count"])} for r in rows)
        return result


def sql_keyword_search(
    query: str, category: str | None = None, limit: int = 24
) -> list[dict[str, Any]]:
    """
    Pencarian SQL Konvensional berbasis pencocokan kata (LIKE) pada nama & kategori produk.
    Digunakan sebagai baseline Sistem Informasi standar untuk dibandingkan dengan AI Multimodal.
    """
    clean = query.strip()
    if not clean:
        return list_products(category=category, limit=limit)

    tokens = [t.strip() for t in clean.split() if len(t.strip()) >= 2]
    if not tokens:
        return []

    # Sistem Informasi tradisional mencari kata yang diketik user di kolom nama & deskripsi singkat
    clauses = []
    params: list[Any] = []
    for tok in tokens:
        like_pat = f"%{tok}%"
        clauses.append("(LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))")
        params.extend([like_pat, like_pat])

    where_sql = " AND ".join(clauses)
    if category and category != "Semua":
        where_sql = f"({where_sql}) AND category = ?"
        params.append(category)

    params.append(limit)
    sql = f"SELECT * FROM products WHERE {where_sql} ORDER BY id DESC LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def create_product(data: dict[str, Any]) -> dict[str, Any]:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sku = data.get("sku") or f"KLA-{random.randint(10000, 99999)}"
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO products (
                sku, name, category, sub_category, gender, color,
                price, stock, description, visual_caption_en, visual_query_id,
                image_filename, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sku,
                data["name"],
                data["category"],
                data.get("sub_category", data["category"]),
                data.get("gender", "Unisex"),
                data.get("color", "Netral"),
                int(data["price"]),
                int(data.get("stock", 15)),
                data.get("description", ""),
                data.get("visual_caption_en", ""),
                data.get("visual_query_id", ""),
                data["image_filename"],
                now,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid)
    prod = get_product_by_id(new_id)
    assert prod is not None
    return prod


def delete_product(product_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        return cur.rowcount > 0


def create_order(
    customer_name: str,
    customer_phone: str,
    shipping_address: str,
    payment_method: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    now = dt.datetime.now()
    invoice = f"INV-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
    created_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        total = 0
        resolved_items = []
        for item in items:
            pid = int(item["product_id"])
            qty = max(1, int(item["quantity"]))
            row = conn.execute(
                "SELECT id, name, price, stock FROM products WHERE id = ?", (pid,)
            ).fetchone()
            if not row:
                continue
            price = int(row["price"])
            total += price * qty
            resolved_items.append(
                {
                    "product_id": pid,
                    "product_name": row["name"],
                    "price": price,
                    "quantity": qty,
                }
            )
            new_stock = max(0, int(row["stock"]) - qty)
            conn.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, pid))

        if not resolved_items:
            raise ValueError("Keranjang belanja kosong atau produk tidak ditemukan.")

        cur = conn.execute(
            """
            INSERT INTO orders (
                invoice_number, customer_name, customer_phone,
                shipping_address, payment_method, total_amount, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Menunggu Konfirmasi', ?)
            """,
            (
                invoice,
                customer_name,
                customer_phone,
                shipping_address,
                payment_method,
                total,
                created_str,
            ),
        )
        order_id = int(cur.lastrowid)

        for ri in resolved_items:
            conn.execute(
                """
                INSERT INTO order_items (order_id, product_id, product_name, price, quantity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, ri["product_id"], ri["product_name"], ri["price"], ri["quantity"]),
            )
        conn.commit()

    return {
        "order_id": order_id,
        "invoice_number": invoice,
        "total_amount": total,
        "item_count": sum(x["quantity"] for x in resolved_items),
        "created_at": created_str,
    }


def list_orders(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        orders = conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for o in orders:
            od = dict(o)
            items = conn.execute(
                "SELECT * FROM order_items WHERE order_id = ?", (od["id"],)
            ).fetchall()
            od["items"] = [dict(i) for i in items]
            result.append(od)
        return result


def update_order_status(order_id: int, status: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?", (status, order_id)
        )
        conn.commit()
        return cur.rowcount > 0


def get_dashboard_stats() -> dict[str, Any]:
    with get_connection() as conn:
        prod_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        revenue = (
            conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders").fetchone()[0]
            or 0
        )
        low_stock = conn.execute(
            "SELECT COUNT(*) FROM products WHERE stock <= 5"
        ).fetchone()[0]
    return {
        "total_products": int(prod_count),
        "total_orders": int(order_count),
        "total_revenue": int(revenue),
        "low_stock_count": int(low_stock),
    }
