/* KALA Architectural Retail Storefront & Multimodal Visual Search Controller */

let allProducts = [];
let visualRawResults = [];
let activeQuickTab = "semua";
let activeTopFilter = "Semua";
let currentReferenceFile = null;
let currentPdpProduct = null;
let currentPdpQty = 1;
let currentPdpSize = "L";

let cart = JSON.parse(localStorage.getItem("kala_cart_v2") || "[]");
let wishlist = JSON.parse(localStorage.getItem("kala_wishlist_v2") || "[]");

const COLOR_HEX_MAP = {
  "Biru Dongker": "#1F2A3C",
  "Biru": "#2C4A7A",
  "Hitam": "#111111",
  "Putih": "#F8F8F6",
  "Abu-abu": "#8C9196",
  "Abu-abu Tua": "#3F4347",
  "Merah": "#B91C1C",
  "Merah Marun": "#651A22",
  "Merah Muda": "#E8B4BC",
  "Hijau": "#3B5E47",
  "Hijau Zaitun": "#555D47",
  "Hijau Toska": "#2A6F73",
  "Coklat": "#6B4C35",
  "Coklat Muda": "#B69574",
  "Krem": "#D8CFC2",
  "Krem Muda": "#EFECE6",
  "Ungu": "#58427C",
  "Ungu Muda": "#C3B1E1",
  "Kuning": "#D9A441",
  "Kuning Mustard": "#B8860B",
  "Oranye": "#C85A32",
  "Perak": "#C0C4C8",
  "Emas": "#C5A059",
  "Kombinasi Warna": "#4A5568",
};

const DEFAULT_PALETTE = ["#1F2A3C", "#F8F8F6", "#555D47", "#111111"];

function formatRupiah(val) {
  return "Rp " + Number(val || 0).toLocaleString("id-ID");
}

function cleanRetailTitle(rawName) {
  return String(rawName || "").replace(/\s*#\d+\s*$/, "").trim();
}

function getSizeRangeLabel(prod) {
  if (prod.category === "Sepatu & Alas Kaki") return "38-44";
  if (prod.category === "Tas & Ransel" || prod.category === "Jam Tangan & Aksesoris") return "Satu Ukuran";
  return prod.gender === "Wanita" ? "XS-XL" : "XS-XXL";
}

function getDeterministicRating(id) {
  const ratings = ["4.9", "4.8", "4.9", "4.7", "5.0", "4.8"];
  const counts = [142, 96, 218, 74, 185, 63, 129, 108];
  return {
    score: ratings[id % ratings.length],
    reviews: counts[id % counts.length] + (id % 17),
  };
}

function isPromoProduct(prod) {
  return prod.id % 5 === 0;
}

function showToast(message) {
  const t = document.getElementById("kala-toast");
  t.textContent = message;
  t.classList.remove("hidden");
  clearTimeout(window._kalaToastTimer);
  window._kalaToastTimer = setTimeout(() => t.classList.add("hidden"), 2800);
}

function showScreen(screenId) {
  ["screen-storefront", "screen-visual-search", "screen-pdp"].forEach((id) => {
    document.getElementById(id).classList.toggle("hidden", id !== screenId);
  });
  if (window.kalaLenis) {
    window.kalaLenis.resize();
    window.kalaLenis.scrollTo(0, { immediate: true });
  } else {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function goHome(event) {
  if (event) event.preventDefault();
  activeTopFilter = "Semua";
  activeQuickTab = "semua";
  document.getElementById("header-search-input").value = "";
  updateQuickTabStyles();
  showScreen("screen-storefront");
  document.getElementById("hero-banner-section").classList.remove("hidden");
  animateHeadingWordsImmediate(document.getElementById("storefront-heading"), "Koleksi Pilihan Minggu Ini");
  renderStorefrontGrid();
}

/* ==================== WISHLIST & BAG ==================== */
function syncBadges() {
  localStorage.setItem("kala_cart_v2", JSON.stringify(cart));
  localStorage.setItem("kala_wishlist_v2", JSON.stringify(wishlist));

  const bagTotalQty = cart.reduce((sum, x) => sum + x.quantity, 0);
  document.getElementById("bag-count-badge").textContent = String(bagTotalQty);

  const wishBadge = document.getElementById("wishlist-badge");
  if (wishlist.length > 0) {
    wishBadge.textContent = String(wishlist.length);
    wishBadge.classList.remove("hidden");
    wishBadge.classList.add("flex");
  } else {
    wishBadge.classList.add("hidden");
    wishBadge.classList.remove("flex");
  }
}

function toggleWishlist(event, productId) {
  event.stopPropagation();
  const idx = wishlist.indexOf(productId);
  if (idx >= 0) {
    wishlist.splice(idx, 1);
    showToast("Dihapus dari daftar keinginan.");
  } else {
    wishlist.push(productId);
    showToast("Disimpan ke daftar keinginan.");
  }
  syncBadges();
  if (!document.getElementById("screen-storefront").classList.contains("hidden")) {
    renderStorefrontGrid();
  } else if (!document.getElementById("screen-visual-search").classList.contains("hidden")) {
    applyVisualClientFilters();
  }
}

/* ==================== RENDER UNIQLO CARD ==================== */
function buildProductCardHtml(prod) {
  const title = cleanRetailTitle(prod.name);
  const imgUrl = `/static/products/${prod.image_filename}`;
  const mainHex = COLOR_HEX_MAP[prod.color] || "#111111";
  const swatches = [mainHex, ...DEFAULT_PALETTE.filter((c) => c !== mainHex)].slice(0, 4);
  const sizeRange = getSizeRangeLabel(prod);
  const rating = getDeterministicRating(prod.id);
  const wished = wishlist.includes(prod.id);
  const promo = isPromoProduct(prod);
  const origPrice = Math.round((prod.price * 1.28) / 10000) * 10000;

  const priceHtml = promo
    ? `<div class="flex items-baseline gap-gutter-sm">
         <p class="font-title text-title-lg text-brand-red tabular-nums">${formatRupiah(prod.price)}</p>
         <span class="font-body text-body-sm text-on-surface-muted line-through tabular-nums">${formatRupiah(origPrice)}</span>
       </div>`
    : `<p class="font-title text-title-lg text-on-surface tabular-nums">${formatRupiah(prod.price)}</p>`;

  return `
    <article onclick="openProductDetail(${prod.id})" class="kala-card group flex flex-col bg-surface cursor-pointer will-change-transform">
      <div class="kala-card-frame relative aspect-[3/4] w-full bg-surface-studio overflow-hidden rounded-none border border-transparent">
        <img
          src="${imgUrl}"
          alt="${title}"
          loading="lazy"
          class="kala-card-img w-full h-full object-contain p-2 will-change-transform"
        >
        <button
          type="button"
          onclick="toggleWishlist(event, ${prod.id})"
          aria-label="Wishlist"
          class="kala-wish-btn absolute top-3 right-3 w-8 h-8 flex items-center justify-center ${wished ? "text-brand-red" : "text-on-surface"} hover:text-brand-red transition-colors duration-state-change"
        >
          <span class="material-symbols-outlined" style="font-size: 20px; font-variation-settings: 'FILL' ${wished ? 1 : 0};">favorite</span>
        </button>
        <button
          type="button"
          onclick="findSimilarFromCard(event, '${imgUrl}', '${title.replace(/'/g, "\\'")}')"
          title="Cari potongan & gaya serupa"
          style="opacity: 0; transform: translateY(8px);"
          class="kala-similar-btn absolute bottom-3 right-3 bg-surface/95 border border-outline px-2.5 py-1.5 flex items-center gap-1 text-on-surface hover:border-outline-strong will-change-transform"
        >
          <span class="material-symbols-outlined" style="font-size: 15px;">photo_camera</span>
          <span class="font-label text-label-sm">Serupa</span>
        </button>
      </div>
      <div class="pt-3 flex flex-col gap-1.5">
        <div class="flex items-center gap-1.5" aria-label="Pilihan warna">
          ${swatches
            .map(
              (hex) =>
                `<span class="kala-swatch w-3 h-3 rounded-full border border-outline inline-block" style="background-color: ${hex};"></span>`
            )
            .join("")}
        </div>
        <div class="flex items-center justify-between text-on-surface-muted font-body text-body-sm">
          <span>${prod.gender}</span>
          <span>${sizeRange}</span>
        </div>
        <h3 class="font-title text-title-md text-on-surface line-clamp-1 group-hover:underline underline-offset-4">
          ${title}
        </h3>
        ${priceHtml}
        <div class="flex items-center gap-1 font-body text-body-sm text-on-surface">
          <span class="material-symbols-outlined" style="font-size: 14px; font-variation-settings: 'FILL' 1;">star</span>
          <span class="tabular-nums">${rating.score} (${rating.reviews})</span>
        </div>
      </div>
    </article>
  `;
}

/* ==================== CATALOG FILTERING ==================== */
async function loadCatalog() {
  const res = await fetch("/api/products?limit=260");
  const data = await res.json();
  allProducts = data.products || [];
  renderStorefrontGrid();
}

function selectQuickTab(tabKey) {
  activeQuickTab = tabKey;
  updateQuickTabStyles();
  renderStorefrontGrid();
}

function updateQuickTabStyles() {
  document.querySelectorAll(".category-tab").forEach((btn) => {
    const active = btn.dataset.qtab === activeQuickTab;
    btn.className = active
      ? "category-tab px-4 py-2.5 bg-primary text-on-primary border border-primary rounded-sm font-label text-label-md whitespace-nowrap transition-colors duration-state-change"
      : "category-tab px-4 py-2.5 bg-surface text-on-surface border border-outline rounded-sm font-label text-label-md whitespace-nowrap transition-colors duration-state-change hover:border-outline-strong";
  });
}

function filterByTopNav(filterType) {
  activeTopFilter = filterType;
  showScreen("screen-storefront");

  const hero = document.getElementById("hero-banner-section");
  const heading = document.getElementById("storefront-heading");

  if (filterType === "Semua") {
    hero.classList.remove("hidden");
    animateHeadingWordsImmediate(heading, "Koleksi Pilihan Minggu Ini");
  } else {
    hero.classList.add("hidden");
    if (filterType === "Promo") animateHeadingWordsImmediate(heading, "Penawaran Terbatas Minggu Ini");
    else if (filterType === "Wishlist") animateHeadingWordsImmediate(heading, "Daftar Keinginan Saya");
    else animateHeadingWordsImmediate(heading, `Koleksi ${filterType}`);
  }
  renderStorefrontGrid();
}

function matchesQuickTab(prod, tab) {
  if (tab === "semua") return true;
  const sub = (prod.sub_category || "").toLowerCase();
  const cat = (prod.category || "").toLowerCase();
  if (tab === "kemeja") return sub.includes("kemeja") || sub.includes("blus") || sub.includes("gaun");
  if (tab === "kaos") return sub.includes("kaos");
  if (tab === "celana") return cat.includes("celana");
  if (tab === "jaket") return sub.includes("jaket") || sub.includes("sweater") || sub.includes("hoodie");
  if (tab === "sepatu") return cat.includes("sepatu");
  if (tab === "tas") return cat.includes("tas") || cat.includes("jam tangan");
  return true;
}

function renderStorefrontGrid() {
  let filtered = allProducts.filter((p) => matchesQuickTab(p, activeQuickTab));

  if (activeTopFilter === "Wanita" || activeTopFilter === "Pria" || activeTopFilter === "Unisex") {
    filtered = filtered.filter((p) => p.gender === activeTopFilter);
  } else if (activeTopFilter === "Promo") {
    filtered = filtered.filter((p) => isPromoProduct(p));
  } else if (activeTopFilter === "Wishlist") {
    filtered = filtered.filter((p) => wishlist.includes(p.id));
  }

  document.getElementById("storefront-count").textContent = `Menampilkan ${filtered.length} produk`;
  const grid = document.getElementById("storefront-grid");

  if (!filtered.length) {
    grid.innerHTML = `
      <div class="col-span-full py-16 text-center border border-outline bg-surface-studio">
        <p class="font-title text-title-md text-on-surface mb-2">Belum ada produk pada kategori ini</p>
        <button type="button" onclick="goHome(event)" class="mt-2 px-5 py-2.5 bg-primary text-on-primary font-label text-label-md rounded-sm">
          Lihat Semua Koleksi
        </button>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.slice(0, 48).map(buildProductCardHtml).join("");
  animateProductGridScroll(grid);
}

/* ==================== MULTIMODAL VISUAL & TEXT SEARCH ==================== */
function triggerCameraUpload() {
  document.getElementById("camera-file-input").click();
}

function handleCameraUpload(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  currentReferenceFile = file;
  const currentQuery = document.getElementById("vs-refinement-input").value.trim() ||
                       document.getElementById("header-search-input").value.trim();
  executeMultimodalSearch(currentQuery, currentReferenceFile);
}

async function findSimilarFromCard(event, imgUrl, prodTitle) {
  if (event) event.stopPropagation();
  try {
    const resp = await fetch(imgUrl);
    const blob = await resp.blob();
    currentReferenceFile = new File([blob], "referensi_produk.jpg", { type: "image/jpeg" });
    document.getElementById("vs-refinement-input").value = "";
    document.getElementById("header-search-input").value = `Pencarian Foto: ${prodTitle}`;
    await executeMultimodalSearch("", currentReferenceFile);
  } catch (err) {
    showToast("Gagal memuat foto referensi.");
  }
}

function removeReferencePhoto() {
  currentReferenceFile = null;
  document.getElementById("camera-file-input").value = "";
  document.getElementById("vs-photo-box").classList.add("hidden");
  document.getElementById("vs-photo-box").classList.remove("flex");
  document.getElementById("vs-attach-btn").classList.remove("hidden");

  const q = document.getElementById("vs-refinement-input").value.trim();
  if (q) {
    executeMultimodalSearch(q, null);
  } else {
    goHome();
  }
}

function submitHeaderSearch(event) {
  event.preventDefault();
  const q = document.getElementById("header-search-input").value.trim();
  if (!q && !currentReferenceFile) return;
  const cleanQ = q.replace(/^Pencarian Foto:\s*/i, "");
  document.getElementById("vs-refinement-input").value = cleanQ;
  executeMultimodalSearch(cleanQ, currentReferenceFile);
}

function submitRefinementSearch(event) {
  event.preventDefault();
  const q = document.getElementById("vs-refinement-input").value.trim();
  if (!q && !currentReferenceFile) return;
  document.getElementById("header-search-input").value = currentReferenceFile
    ? `Pencarian Foto${q ? ": " + q : ""}`
    : q;
  executeMultimodalSearch(q, currentReferenceFile);
}

async function executeMultimodalSearch(queryText, imageFile) {
  showScreen("screen-visual-search");

  const photoBox = document.getElementById("vs-photo-box");
  const attachBtn = document.getElementById("vs-attach-btn");
  if (imageFile) {
    document.getElementById("vs-reference-img").src = URL.createObjectURL(imageFile);
    photoBox.classList.remove("hidden");
    photoBox.classList.add("flex");
    attachBtn.classList.add("hidden");
  } else {
    photoBox.classList.add("hidden");
    photoBox.classList.remove("flex");
    attachBtn.classList.remove("hidden");
  }

  // Reset client sub-filters
  document.getElementById("vs-sort-select").value = "sesuai";
  document.getElementById("vs-gender-select").value = "";
  document.getElementById("vs-color-select").value = "";
  document.getElementById("vs-price-select").value = "";

  const applyBtn = document.getElementById("vs-apply-btn");
  applyBtn.disabled = true;
  applyBtn.textContent = "Mencari...";
  document.getElementById("vs-results-heading").textContent = "Mencari koleksi yang paling sesuai...";

  try {
    const fd = new FormData();
    fd.append("query_text", queryText || "");
    fd.append("mode", "multimodal_rerank");
    fd.append("category", "Semua");
    fd.append("top_k", "32");
    if (imageFile) {
      fd.append("query_image", imageFile, imageFile.name || "referensi.jpg");
    }

    const res = await fetch("/api/search", { method: "POST", body: fd });
    const data = await res.json();
    visualRawResults = data.products || [];
    applyVisualClientFilters();
  } catch (err) {
    showToast("Terjadi kendala saat mencari produk.");
  } finally {
    applyBtn.disabled = false;
    applyBtn.textContent = "Terapkan";
  }
}

function applyVisualClientFilters() {
  let list = [...visualRawResults];
  const sortVal = document.getElementById("vs-sort-select").value;
  const genVal = document.getElementById("vs-gender-select").value;
  const colVal = document.getElementById("vs-color-select").value;
  const prcVal = document.getElementById("vs-price-select").value;

  if (genVal) {
    list = list.filter((p) => p.gender === genVal);
  }
  if (colVal) {
    list = list.filter((p) => (p.color || "").toLowerCase().includes(colVal.toLowerCase()));
  }
  if (prcVal === "under-250") {
    list = list.filter((p) => p.price < 250000);
  } else if (prcVal === "250-450") {
    list = list.filter((p) => p.price >= 250000 && p.price <= 450000);
  } else if (prcVal === "above-450") {
    list = list.filter((p) => p.price > 450000);
  }

  if (sortVal === "harga-rendah") {
    list.sort((a, b) => a.price - b.price);
  } else if (sortVal === "harga-tinggi") {
    list.sort((a, b) => b.price - a.price);
  }

  animateHeadingWordsImmediate(
    document.getElementById("vs-results-heading"),
    `Menampilkan ${list.length} produk dengan potongan dan gaya serupa`
  );

  const grid = document.getElementById("vs-results-grid");
  if (!list.length) {
    grid.innerHTML = `
      <div class="col-span-full py-16 text-center border border-outline bg-surface-studio">
        <p class="font-title text-title-md text-on-surface">Tidak ada produk yang cocok dengan filter tambahan di atas.</p>
      </div>
    `;
    return;
  }
  grid.innerHTML = list.map(buildProductCardHtml).join("");
  animateProductGridScroll(grid);
}

/* ==================== PRODUCT DETAIL PAGE (PDP) ==================== */
async function openProductDetail(productId) {
  let prod = allProducts.find((p) => p.id === productId);
  if (!prod) {
    const res = await fetch(`/api/products/${productId}`);
    if (!res.ok) return;
    prod = await res.json();
  }
  currentPdpProduct = prod;
  currentPdpQty = 1;
  document.getElementById("pdp-qty-val").textContent = "1";

  const title = cleanRetailTitle(prod.name);
  const imgUrl = `/static/products/${prod.image_filename}`;
  const rating = getDeterministicRating(prod.id);

  document.getElementById("pdp-bc-gender").textContent = prod.gender;
  document.getElementById("pdp-bc-subcat").textContent = prod.sub_category;
  document.getElementById("pdp-bc-title").textContent = title;
  document.getElementById("pdp-sku-line").textContent = `${prod.gender} • Kode Produk ${prod.sku}`;
  animateHeadingWordsImmediate(document.getElementById("pdp-title"), title);
  document.getElementById("pdp-rating").textContent = `${rating.score} (${rating.reviews} ulasan)`;
  document.getElementById("pdp-color-label").textContent = prod.color;
  document.getElementById("pdp-description").textContent =
    prod.description ||
    "Dibuat dengan material pilihan berkualitas tinggi yang nyaman di kulit sepanjang hari dengan jahitan presisi khas KALA.";
  document.getElementById("pdp-stock-info").textContent =
    `Tersedia ${prod.stock} potong siap kirim hari ini dari gudang utama Jakarta, Bandung, dan Surabaya.`;

  // Price block
  const promo = isPromoProduct(prod);
  const origPrice = Math.round((prod.price * 1.28) / 10000) * 10000;
  document.getElementById("pdp-price-block").innerHTML = promo
    ? `<p class="font-headline text-headline-md text-brand-red font-bold tabular-nums">${formatRupiah(prod.price)}</p>
       <span class="font-body text-body-md text-on-surface-muted line-through tabular-nums">${formatRupiah(origPrice)}</span>`
    : `<p class="font-headline text-headline-md text-on-surface font-bold tabular-nums">${formatRupiah(prod.price)}</p>`;

  // 2x2 Studio Gallery (Utama, Detail Zoom Kain, Detail Potongan Atas, Detail Potongan Bawah)
  document.getElementById("pdp-gallery").innerHTML = `
    <div class="aspect-[3/4] w-full bg-surface-studio overflow-hidden rounded-none">
      <img src="${imgUrl}" alt="${title}" class="w-full h-full object-contain p-4">
    </div>
    <div class="aspect-[3/4] w-full bg-surface-studio overflow-hidden rounded-none">
      <img src="${imgUrl}" alt="Detail tekstur ${title}" class="w-full h-full object-cover scale-150 object-center">
    </div>
    <div class="aspect-[3/4] w-full bg-surface-studio overflow-hidden rounded-none">
      <img src="${imgUrl}" alt="Detail kerah ${title}" class="w-full h-full object-cover scale-125 object-top">
    </div>
    <div class="aspect-[3/4] w-full bg-surface-studio overflow-hidden rounded-none">
      <img src="${imgUrl}" alt="Siluet penuh ${title}" class="w-full h-full object-contain p-8">
    </div>
  `;

  // Color swatches
  const mainHex = COLOR_HEX_MAP[prod.color] || "#111111";
  document.getElementById("pdp-color-swatches").innerHTML = `
    <button type="button" class="w-9 h-9 p-0.5 border-2 border-outline-strong rounded-none">
      <span class="block w-full h-full border border-outline" style="background-color: ${mainHex};"></span>
    </button>
  `;

  // Size boxes
  const sizes =
    prod.category === "Sepatu & Alas Kaki"
      ? ["39", "40", "41", "42", "43", "44"]
      : prod.category === "Tas & Ransel" || prod.category === "Jam Tangan & Aksesoris"
      ? ["ALL"]
      : ["XS", "S", "M", "L", "XL", "XXL"];

  currentPdpSize = sizes.includes("L") ? "L" : sizes[0];
  renderPdpSizes(sizes);

  // Wire Visual Similar buttons
  const simTrigger = () => findSimilarFromCard(null, imgUrl, title);
  document.getElementById("pdp-visual-similar-btn").onclick = simTrigger;
  document.getElementById("pdp-see-all-similar").onclick = simTrigger;

  showScreen("screen-pdp");
  loadPdpRelatedVisualMatches(prod, imgUrl);
}

function renderPdpSizes(sizes) {
  document.getElementById("pdp-size-label").textContent = currentPdpSize;
  document.getElementById("pdp-size-boxes").innerHTML = sizes
    .map((sz) => {
      const active = sz === currentPdpSize;
      return `
        <button
          type="button"
          onclick="selectPdpSize('${sz}', ${JSON.stringify(sizes).replace(/"/g, "&quot;")})"
          class="flex items-center justify-center ${active ? "border-2 border-outline-strong font-bold" : "border border-outline hover:border-outline-strong"} bg-surface text-on-surface font-label text-label-md rounded-none transition-colors duration-state-change"
          style="min-width: 48px; height: 48px; padding: 0 12px;"
        >${sz}</button>
      `;
    })
    .join("");
}

function selectPdpSize(sz, sizes) {
  currentPdpSize = sz;
  renderPdpSizes(sizes);
}

function adjustPdpQty(delta) {
  currentPdpQty = Math.max(1, currentPdpQty + delta);
  document.getElementById("pdp-qty-val").textContent = String(currentPdpQty);
}

function toggleAccordion(btn) {
  const panel = btn.nextElementSibling;
  const icon = btn.querySelector(".acc-icon");
  const isHidden = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !isHidden);
  icon.textContent = isHidden ? "expand_less" : "expand_more";
}

async function loadPdpRelatedVisualMatches(prod, imgUrl) {
  const relGrid = document.getElementById("pdp-related-grid");
  relGrid.innerHTML = `<p class="col-span-full font-body text-body-sm text-on-surface-muted">Memuat rekomendasi serupa...</p>`;
  try {
    const imgResp = await fetch(imgUrl);
    const blob = await imgResp.blob();
    const fd = new FormData();
    fd.append("query_text", "");
    fd.append("mode", "multimodal_rerank");
    fd.append("category", "Semua");
    fd.append("top_k", "6");
    fd.append("query_image", new File([blob], "pdp.jpg", { type: "image/jpeg" }));

    const res = await fetch("/api/search", { method: "POST", body: fd });
    const data = await res.json();
    const matches = (data.products || []).filter((x) => x.id !== prod.id).slice(0, 4);
    relGrid.innerHTML = matches.map(buildProductCardHtml).join("");
    animateProductGridScroll(relGrid);
  } catch {
    const fallback = allProducts.filter((x) => x.category === prod.category && x.id !== prod.id).slice(0, 4);
    relGrid.innerHTML = fallback.map(buildProductCardHtml).join("");
    animateProductGridScroll(relGrid);
  }
}

/* ==================== SHOPPING BAG & CHECKOUT ==================== */
function addCurrentPdpToBag() {
  if (!currentPdpProduct) return;
  const key = `${currentPdpProduct.id}_${currentPdpSize}`;
  const found = cart.find((x) => x.key === key);
  if (found) {
    found.quantity += currentPdpQty;
  } else {
    cart.push({
      key,
      id: currentPdpProduct.id,
      name: cleanRetailTitle(currentPdpProduct.name),
      size: currentPdpSize,
      color: currentPdpProduct.color,
      price: currentPdpProduct.price,
      image_filename: currentPdpProduct.image_filename,
      quantity: currentPdpQty,
    });
  }
  syncBadges();
  toggleBagDrawer(true);
}

function toggleBagDrawer(open) {
  document.getElementById("bag-backdrop").classList.toggle("hidden", !open);
  const drawer = document.getElementById("bag-drawer");
  drawer.classList.toggle("hidden", !open);
  drawer.classList.toggle("flex", open);
  if (window.kalaLenis) {
    if (open) window.kalaLenis.stop();
    else window.kalaLenis.start();
  }
  if (open) renderBagItems();
}

function changeBagItemQty(key, delta) {
  const idx = cart.findIndex((x) => x.key === key);
  if (idx === -1) return;
  cart[idx].quantity += delta;
  if (cart[idx].quantity <= 0) cart.splice(idx, 1);
  syncBadges();
  renderBagItems();
}

function renderBagItems() {
  const container = document.getElementById("bag-items-container");
  const form = document.getElementById("bag-checkout-form");

  if (!cart.length) {
    container.innerHTML = `
      <div class="py-16 text-center">
        <p class="font-title text-title-md text-on-surface mb-1">Keranjang belanja Anda kosong</p>
        <p class="font-body text-body-sm text-on-surface-muted">Jelajahi koleksi terbaru atau gunakan pencarian foto untuk menemukan gaya Anda.</p>
      </div>
    `;
    form.classList.add("hidden");
    form.classList.remove("flex");
    return;
  }

  form.classList.remove("hidden");
  form.classList.add("flex");

  let subtotal = 0;
  container.innerHTML = cart
    .map((item) => {
      subtotal += item.price * item.quantity;
      return `
        <div class="flex gap-gutter-md py-4 border-b border-outline">
          <div class="w-20 h-24 bg-surface-studio flex-shrink-0 overflow-hidden">
            <img src="/static/products/${item.image_filename}" alt="${item.name}" class="w-full h-full object-contain p-1">
          </div>
          <div class="flex-1 flex flex-col justify-between">
            <div>
              <h4 class="font-title text-title-md text-on-surface">${item.name}</h4>
              <p class="font-body text-body-sm text-on-surface-muted mt-0.5">Warna: ${item.color} • Ukuran: ${item.size}</p>
            </div>
            <div class="flex items-center justify-between mt-2">
              <div class="flex items-center border border-outline">
                <button type="button" onclick="changeBagItemQty('${item.key}', -1)" class="w-7 h-7 flex items-center justify-center text-on-surface hover:bg-surface-studio">-</button>
                <span class="w-8 text-center font-label text-label-sm tabular-nums">${item.quantity}</span>
                <button type="button" onclick="changeBagItemQty('${item.key}', 1)" class="w-7 h-7 flex items-center justify-center text-on-surface hover:bg-surface-studio">+</button>
              </div>
              <span class="font-title text-title-md text-on-surface tabular-nums">${formatRupiah(item.price * item.quantity)}</span>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  document.getElementById("bag-subtotal-text").textContent = formatRupiah(subtotal);
}

async function submitBagOrder(event) {
  event.preventDefault();
  const btn = document.getElementById("bag-checkout-btn");
  btn.disabled = true;
  btn.textContent = "Memproses Pesanan...";

  try {
    const fd = new FormData(event.target);
    const payload = {
      customer_name: fd.get("customer_name"),
      customer_phone: fd.get("customer_phone"),
      shipping_address: fd.get("shipping_address"),
      payment_method: fd.get("payment_method"),
      items: cart.map((x) => ({ product_id: x.id, quantity: x.quantity })),
    };

    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      cart = [];
      syncBadges();
      event.target.reset();
      toggleBagDrawer(false);
      showToast(`Pesanan berhasil dibuat (${data.order.invoice_number})`);
    } else {
      showToast(data.detail || "Gagal memproses pesanan.");
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Lanjutkan Pemesanan";
  }
}

/* ==================== GSAP + SCROLLTRIGGER WORD REVEALS ==================== */
const prefersReducedMotion = () =>
  window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function splitTextIntoMaskedWords(el, explicitText) {
  if (!el) return [];
  const raw = (explicitText !== undefined ? explicitText : el.getAttribute("data-raw-text") || el.textContent || "").trim();
  if (!raw) return [];
  el.setAttribute("data-raw-text", raw);
  el.setAttribute("aria-label", raw);
  const words = raw.split(/\s+/);
  el.innerHTML = words
    .map(
      (word) =>
        `<span class="gsap-word-mask" aria-hidden="true"><span class="gsap-word-inner">${word}</span></span>`
    )
    .join(" ");
  return Array.from(el.querySelectorAll(".gsap-word-inner"));
}

function animateHeadingWordsImmediate(el, newText) {
  if (!el) return;
  if (!window.gsap || prefersReducedMotion()) {
    if (newText !== undefined) el.textContent = newText;
    return;
  }
  const wordSpans = splitTextIntoMaskedWords(el, newText);
  if (!wordSpans.length) return;
  gsap.killTweensOf(wordSpans);
  gsap.fromTo(
    wordSpans,
    { yPercent: 115, opacity: 0 },
    {
      yPercent: 0,
      opacity: 1,
      duration: 0.7,
      stagger: 0.055,
      ease: "power3.out",
      overwrite: "auto",
    }
  );
}

function bindScrollWordReveal(el) {
  if (!el || !window.gsap || !window.ScrollTrigger || prefersReducedMotion()) return;
  const wordSpans = splitTextIntoMaskedWords(el);
  if (!wordSpans.length) return;

  gsap.set(wordSpans, { yPercent: 115, opacity: 0 });
  gsap.to(wordSpans, {
    yPercent: 0,
    opacity: 1,
    duration: 0.8,
    stagger: 0.06,
    ease: "power3.out",
    scrollTrigger: {
      trigger: el,
      start: "top 88%",
      toggleActions: "play none none none",
    },
  });
}

function animateProductGridScroll(gridEl) {
  if (!gridEl || prefersReducedMotion()) return;
  const cards = Array.from(gridEl.querySelectorAll(".kala-card"));
  if (!cards.length) return;

  const M = window.Motion;
  if (!M || typeof M.animate !== "function") {
    if (window.ScrollTrigger) ScrollTrigger.refresh();
    return;
  }

  cards.forEach((card, idx) => {
    const img = card.querySelector(".kala-card-img");
    const frame = card.querySelector(".kala-card-frame");
    const simBtn = card.querySelector(".kala-similar-btn");
    const swatches = card.querySelectorAll(".kala-swatch");

    // 1. Animasi Masuk Card dengan Motion inView + Stagger per Kolom
    card.style.opacity = "0";
    card.style.transform = "translateY(28px) scale(0.97)";

    const colDelay = (idx % 4) * 0.065;
    if (typeof M.inView === "function") {
      M.inView(
        card,
        () => {
          M.animate(
            card,
            { opacity: [0, 1], y: [28, 0], scale: [0.97, 1] },
            { duration: 0.56, delay: colDelay, ease: [0.22, 1, 0.36, 1] }
          );
          if (img) {
            M.animate(
              img,
              { scale: [1.06, 1] },
              { duration: 0.65, delay: colDelay, ease: [0.22, 1, 0.36, 1] }
            );
          }
        },
        { amount: 0.12 }
      );
    } else {
      M.animate(
        card,
        { opacity: [0, 1], y: [28, 0], scale: [0.97, 1] },
        { duration: 0.56, delay: colDelay, ease: [0.22, 1, 0.36, 1] }
      );
    }

    // 2. Animasi Interaktif Hover Card dengan Fisika Spring Motion
    if (typeof M.hover === "function") {
      M.hover(card, () => {
        M.animate(card, { y: -6 }, { type: "spring", stiffness: 380, damping: 28 });
        if (frame) frame.style.borderColor = "#E5E5E5";
        if (img) {
          M.animate(img, { scale: 1.07 }, { type: "spring", stiffness: 280, damping: 24 });
        }
        if (simBtn) {
          M.animate(simBtn, { opacity: 1, y: 0 }, { duration: 0.2, ease: [0.22, 1, 0.36, 1] });
        }
        if (swatches.length && typeof M.stagger === "function") {
          M.animate(
            swatches,
            { scale: [1, 1.22, 1] },
            { duration: 0.28, delay: M.stagger(0.035) }
          );
        }

        return () => {
          M.animate(card, { y: 0 }, { type: "spring", stiffness: 380, damping: 30 });
          if (frame) frame.style.borderColor = "transparent";
          if (img) {
            M.animate(img, { scale: 1 }, { type: "spring", stiffness: 280, damping: 26 });
          }
          if (simBtn) {
            M.animate(simBtn, { opacity: 0, y: 8 }, { duration: 0.16 });
          }
        };
      });
    }

    // 3. Efek Tekan Taktil (Motion press)
    if (typeof M.press === "function") {
      M.press(card, () => {
        M.animate(card, { scale: 0.985 }, { duration: 0.1 });
        return () => {
          M.animate(card, { scale: 1 }, { type: "spring", stiffness: 450, damping: 28 });
        };
      });
    }
  });

  if (window.kalaLenis) window.kalaLenis.resize();
  if (window.ScrollTrigger) ScrollTrigger.refresh();
}

function initLenisSmoothScroll() {
  if (typeof window.Lenis !== "function" || prefersReducedMotion()) return;

  const lenis = new window.Lenis({
    duration: 1.15,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
    wheelMultiplier: 1.0,
    touchMultiplier: 1.5,
  });
  window.kalaLenis = lenis;

  if (window.gsap && window.ScrollTrigger) {
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((time) => {
      lenis.raf(time * 1000);
    });
    gsap.ticker.lagSmoothing(0);
  } else {
    function raf(time) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);
  }

  // Smooth anchor scrolling (misal: "Lihat Koleksi" -> #koleksi, "Panduan Ukuran" -> #panduan-ukuran-acc)
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", (e) => {
      const targetId = anchor.getAttribute("href");
      if (!targetId || targetId === "#") return;
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        lenis.scrollTo(targetEl, { offset: -76, duration: 1.15 });
      }
    });
  });
}

function initGsapAnimations() {
  if (!window.gsap || !window.ScrollTrigger || prefersReducedMotion()) return;
  gsap.registerPlugin(ScrollTrigger);

  // 1. Hero Banner Orchestrated Word-by-Word Reveal + Subtle Scroll Parallax
  const heroHeadline = document.getElementById("hero-headline");
  const heroWords = splitTextIntoMaskedWords(heroHeadline);
  const heroEyebrow = document.getElementById("hero-eyebrow");
  const heroSubprice = document.getElementById("hero-subprice");
  const heroCtas = document.getElementById("hero-ctas");
  const heroImg = document.getElementById("hero-banner-img");

  const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
  if (heroImg) {
    tl.fromTo(heroImg, { scale: 1.07 }, { scale: 1.0, duration: 1.4, ease: "power2.out" }, 0);
    gsap.to(heroImg, {
      yPercent: 10,
      ease: "none",
      scrollTrigger: {
        trigger: "#hero-banner-section",
        start: "top top",
        end: "bottom top",
        scrub: true,
      },
    });
  }
  if (heroEyebrow) {
    tl.fromTo(heroEyebrow, { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 }, 0.1);
  }
  if (heroWords.length) {
    tl.fromTo(
      heroWords,
      { yPercent: 120, opacity: 0 },
      { yPercent: 0, opacity: 1, duration: 0.82, stagger: 0.065 },
      0.22
    );
  }
  if (heroSubprice) {
    tl.fromTo(heroSubprice, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55 }, "-=0.35");
  }
  if (heroCtas) {
    tl.fromTo(heroCtas, { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55 }, "-=0.4");
  }

  // 2. ScrollTrigger Word-by-Word Reveals on Section Headings
  bindScrollWordReveal(document.getElementById("storefront-heading"));
  bindScrollWordReveal(document.getElementById("pdp-related-heading"));
  document.querySelectorAll("[data-scroll-words]").forEach((el) => bindScrollWordReveal(el));
}

document.addEventListener("DOMContentLoaded", () => {
  syncBadges();
  initLenisSmoothScroll();
  initGsapAnimations();
  loadCatalog();
});
