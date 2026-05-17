/**
 * raffle.js — Lógica da página pública de sorteio
 */
"use strict";

// ── Constants ─────────────────────────────────────────────────────────────
const COMPACT_THRESHOLD = 500;   // switch to compact pixel-map above this count
const PAGE_SIZE = 1000;          // numbers per page in compact mode
const MIN_AVAILABLE_ON_INITIAL_PAGE = 20;

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  quotas: [],         // [{id, number, status, paid}]
  selected: new Set(),
  filterStatus: "all", // "all" | "available" | "reserved" | "paid" | "unpaid"
  pendingOrder: null,  // {token, pix_payload, qr_code_base64, expires_at, total, numbers}
  compactPage: 0,
  lastCartCount: 0,
  autoFocusedAllPage: false,
};

// ── Helpers ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function fmtBRL(n) {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function toast(msg, type = "") {
  const el = $("rfToast");
  el.textContent = msg;
  el.className = `rf-toast${type ? " " + type : ""}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 4000);
}

async function apiJson(url, opts = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(body.detail || r.statusText);
  }
  return r.json();
}

// ── Countdown ─────────────────────────────────────────────────────────────
function initCountdown() {
  const el = $("countdown");
  if (!el) return;
  const target = new Date(el.dataset.target).getTime();
  const tick = () => {
    const diff = target - Date.now();
    if (diff <= 0) {
      el.innerHTML = "<span style='color:var(--muted)'>Sorteio encerrado</span>";
      return;
    }
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    $("cd-days").textContent = String(d).padStart(2, "0");
    $("cd-hours").textContent = String(h).padStart(2, "0");
    $("cd-mins").textContent = String(m).padStart(2, "0");
    $("cd-secs").textContent = String(s).padStart(2, "0");
  };
  tick();
  setInterval(tick, 1000);
}

// ── Load Quotas ───────────────────────────────────────────────────────────
async function loadRaffle() {
  try {
    const data = await apiJson(`/api/v2/raffles/${CAMPAIGN_SLUG}`);
    state.quotas = data.quotas || [];
    updateProgress(data.stats);
    updateFilterCounts();
    renderGrid();

    if (WINNER_QUOTA_ID && data.status === "drawn") {
      const w = state.quotas.find(q => q.id === WINNER_QUOTA_ID);
      if (w) {
        const banner = $("winnerBanner");
        if (banner) banner.textContent = `🏆 Vencedor: Número ${w.number} — ${w.reserved_by || ""}`;
      }
    }
  } catch (e) {
    $("rfGrid").innerHTML = `<div class="rf-empty">Erro ao carregar números. ${e.message}</div>`;
  }
}

function updateProgress(stats) {
  if (!stats) return;
  const sold = (stats.paid || 0) + (stats.reserved || 0);
  const total = stats.total || 1;
  const pct = Math.min((sold / total) * 100, 100);
  const availablePct = Math.max(0, 100 - pct);
  const fill = $("progressFill");
  if (fill) fill.style.width = pct.toFixed(1) + "%";
  const pctEl = $("statPct");
  if (pctEl) pctEl.textContent = pct.toFixed(1) + "%";
  const soldPctEl = $("statSoldPct");
  if (soldPctEl) soldPctEl.textContent = pct.toFixed(1) + "%";
  const availPctEl = $("statAvailPct");
  if (availPctEl) availPctEl.textContent = availablePct.toFixed(1) + "%";
  const heroPctEl = $("heroStatPct");
  if (heroPctEl) heroPctEl.textContent = pct.toFixed(1) + "%";
}

// ── Grid Rendering ─────────────────────────────────────────────────────────
function renderGrid() {
  const grid = $("rfGrid");
  let quotas = state.quotas;

  // Apply status filter
  if (state.filterStatus === "available") {
    quotas = quotas.filter(q => q.status === "available" && !state.selected.has(q.number));
  } else if (state.filterStatus === "reserved") {
    quotas = quotas.filter(q => q.status === "reserved");
  } else if (state.filterStatus === "paid") {
    quotas = quotas.filter(q => q.status === "paid");
  } else if (state.filterStatus === "unpaid") {
    quotas = quotas.filter(q => q.status === "reserved");
  }

  if (!quotas.length) {
    grid.className = "rf-grid";
    grid.onclick = null;
    grid.onmouseover = null;
    grid.onmousemove = null;
    grid.onmouseleave = null;
    grid.innerHTML = '<div class="rf-empty">Nenhum número encontrado.</div>';
    const badge = $("rfCompactBadge");
    if (badge) badge.classList.add("hidden");
    updatePagination(0, 0);
    return;
  }

  if (state.quotas.length > COMPACT_THRESHOLD) {
    renderCompactGrid(quotas);
  } else {
    renderNormalGrid(quotas);
  }
}

function renderNormalGrid(quotas) {
  const grid = $("rfGrid");
  grid.className = "rf-grid";
  grid.onclick = null;
  grid.onmouseover = null;
  grid.onmousemove = null;
  grid.onmouseleave = null;
  const badge = $("rfCompactBadge");
  if (badge) badge.classList.add("hidden");

  const frag = document.createDocumentFragment();
  quotas.forEach(q => {
    const btn = document.createElement("button");
    btn.className = "rf-num";
    btn.textContent = q.number;
    btn.dataset.number = q.number;
    btn.dataset.id = q.id;

    if (q.id === WINNER_QUOTA_ID) {
      btn.classList.add("winner-glow");
      btn.title = "Número vencedor!";
      btn.disabled = true;
    } else if (state.selected.has(q.number)) {
      btn.classList.add("selected");
    } else if (q.paid) {
      btn.classList.add("paid");
      btn.disabled = true;
      btn.title = "Número pago";
    } else if (q.status === "reserved") {
      btn.classList.add("reserved");
      btn.disabled = true;
      btn.title = "Número reservado";
    } else {
      btn.addEventListener("click", () => toggleNumber(q.number));
    }
    frag.appendChild(btn);
  });

  grid.innerHTML = "";
  grid.appendChild(frag);
  updatePagination(0, 0);
}

function renderCompactGrid(quotas) {
  const grid = $("rfGrid");
  grid.className = "rf-grid rf-compact-grid";

  const totalPages = Math.ceil(quotas.length / PAGE_SIZE);
  let targetPage = Math.max(0, Math.min(state.compactPage, totalPages - 1));

  // No modo "Todos", na primeira carga tenta abrir direto em uma página
  // com ao menos MIN_AVAILABLE_ON_INITIAL_PAGE números disponíveis para compra.
  // Se não existir, usa a página com maior quantidade de disponíveis.
  if (state.filterStatus === "all" && !state.autoFocusedAllPage) {
    let bestPage = 0;
    let bestCount = -1;

    for (let p = 0; p < totalPages; p++) {
      const startIdx = p * PAGE_SIZE;
      const endIdx = startIdx + PAGE_SIZE;
      const availableCount = quotas.slice(startIdx, endIdx).reduce((acc, q) => {
        const isAvailable = q.status === "available" && !q.paid && !state.selected.has(q.number);
        return acc + (isAvailable ? 1 : 0);
      }, 0);

      if (availableCount >= MIN_AVAILABLE_ON_INITIAL_PAGE) {
        bestPage = p;
        bestCount = availableCount;
        break;
      }

      if (availableCount > bestCount) {
        bestCount = availableCount;
        bestPage = p;
      }
    }

    targetPage = bestPage;
    state.autoFocusedAllPage = true;
  }

  const page = targetPage;
  state.compactPage = page;

  const start = page * PAGE_SIZE;
  const pageQuotas = quotas.slice(start, start + PAGE_SIZE);

  const frag = document.createDocumentFragment();
  pageQuotas.forEach(q => {
    const btn = document.createElement("button");
    btn.className = "rf-compact-num";
    btn.dataset.number = q.number;

    if (q.id === WINNER_QUOTA_ID) {
      btn.classList.add("winner");
    } else if (state.selected.has(q.number)) {
      btn.classList.add("selected");
    } else if (q.paid) {
      btn.classList.add("paid");
    } else if (q.status === "reserved") {
      btn.classList.add("reserved");
    }

    frag.appendChild(btn);
  });

  grid.innerHTML = "";
  grid.appendChild(frag);

  // Event delegation: click
  grid.onclick = (e) => {
    const btn = e.target.closest(".rf-compact-num");
    if (!btn) return;
    if (btn.classList.contains("paid") || btn.classList.contains("reserved") || btn.classList.contains("winner")) return;
    toggleNumber(parseInt(btn.dataset.number));
  };

  // Event delegation: hover tooltip
  const tooltip = $("rfNumTooltip");
  if (tooltip) {
    grid.onmouseover = (e) => {
      const btn = e.target.closest(".rf-compact-num");
      if (!btn) { tooltip.style.display = "none"; return; }
      const num = parseInt(btn.dataset.number);
      let label = `Nº ${num}`;
      if (btn.classList.contains("selected"))  label += " · Selecionado";
      else if (btn.classList.contains("paid"))     label += " · Pago";
      else if (btn.classList.contains("reserved")) label += " · Reservado";
      else if (btn.classList.contains("winner"))   label += " · Vencedor!";
      else                                          label += " · Disponível";
      tooltip.textContent = label;
      tooltip.style.display = "block";
    };
    grid.onmousemove = (e) => {
      tooltip.style.left = (e.clientX + 14) + "px";
      tooltip.style.top  = (e.clientY - 34) + "px";
    };
    grid.onmouseleave = () => {
      tooltip.style.display = "none";
    };
  }

  const badge = $("rfCompactBadge");
  if (badge) {
    badge.classList.remove("hidden");
    badge.textContent = isMobileViewport()
      ? "Visualização compacta ativa"
      : "Visualização compacta ativa. Passe o cursor para identificar um número.";
  }

  updatePagination(page, totalPages, start, Math.min(start + PAGE_SIZE, quotas.length));
}

function updatePagination(page, totalPages, rangeStart, rangeEnd) {
  const pag = $("rfPagination");
  if (!pag) return;
  if (totalPages <= 1) {
    pag.classList.add("hidden");
    return;
  }
  pag.classList.remove("hidden");
  const info = $("rfPageInfo");
  if (info) {
    info.textContent = totalPages > 1 ? `Página ${page + 1}` : "";
  }
  const prev = $("rfPagePrev");
  const next = $("rfPageNext");
  if (prev) prev.disabled = page === 0;
  if (next) next.disabled = page >= totalPages - 1;
}

window.changePage = function(delta) {
  state.compactPage = Math.max(0, state.compactPage + delta);
  renderGrid();
  $("rfGrid").scrollIntoView({ behavior: "smooth", block: "start" });
};

function toggleNumber(num) {
  if (RAFFLE_STATUS !== "active") {
    toast("Este sorteio não está ativo para compras.", "error");
    return;
  }
  if (state.selected.has(num)) {
    state.selected.delete(num);
  } else {
    if (state.selected.size >= MAX_PER_PERSON) {
      toast(`Limite de ${MAX_PER_PERSON} números por pessoa.`, "error");
      return;
    }
    state.selected.add(num);
  }
  renderGrid();
  updateCart();
}

// ── Cart ──────────────────────────────────────────────────────────────────
const CART_DETAIL_LIMIT = 20;

function isMobileViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function openMobileCart() {
  if (!isMobileViewport()) return;
  $("rfCart")?.classList.add("open");
  $("rfCartBackdrop")?.classList.remove("hidden");
  $("btnOpenMobileCart")?.setAttribute("aria-expanded", "true");
  document.body.classList.add("rf-cart-open");
}

function closeMobileCart() {
  $("rfCart")?.classList.remove("open");
  $("rfCartBackdrop")?.classList.add("hidden");
  $("btnOpenMobileCart")?.setAttribute("aria-expanded", "false");
  document.body.classList.remove("rf-cart-open");
}

function syncMobileCartVisibility(count, total) {
  const fab = $("rfCartFab");
  const meta = $("cartFabMeta");
  const totalEl = $("cartFabTotal");
  const btn = $("btnOpenMobileCart");
  if (!fab || !meta || !totalEl || !btn) return;

  if (!isMobileViewport()) {
    fab.classList.remove("visible", "has-items");
    closeMobileCart();
    return;
  }

  fab.classList.add("visible");
  fab.classList.toggle("has-items", count > 0);
  meta.textContent = count > 0
    ? `${count.toLocaleString("pt-BR")} número(s) selecionado(s)`
    : "Nenhum número selecionado";
  totalEl.textContent = count > 0 ? fmtBRL(total) : "Escolha";
  btn.disabled = false;
}

function pulseMobileCartFab() {
  const fab = $("rfCartFab");
  if (!fab || !isMobileViewport()) return;
  fab.classList.remove("bump");
  void fab.offsetWidth;
  fab.classList.add("bump");
}

function syncQuickBuyOptions() {
  const input = $("quickQty");
  if (input) {
    input.max = String(MAX_PER_PERSON);
    if (parseInt(input.value || "0", 10) > MAX_PER_PERSON) {
      input.value = String(MAX_PER_PERSON);
    }
  }
  document.querySelectorAll(".rf-qty-btn").forEach(btn => {
    const value = parseInt(btn.textContent || "0", 10);
    const allowed = value > 0 && value <= MAX_PER_PERSON;
    btn.hidden = !allowed;
    btn.disabled = !allowed;
  });
}

function updateCart() {
  const nums = [...state.selected].sort((a, b) => a - b);
  const count = nums.length;
  const total = count * PRICE_PER_QUOTA;

  $("cartCount").textContent = count;

  const itemsEl = $("cartItems");
  if (!count) {
    itemsEl.innerHTML = '<div class="rf-cart-empty">Nenhum número selecionado</div>';
    $("cartTotal").style.display = "none";
    $("btnCheckout").disabled = true;
    syncMobileCartVisibility(count, total);
    state.lastCartCount = count;
    return;
  }

  if (count <= CART_DETAIL_LIMIT) {
    itemsEl.innerHTML = nums.map(n => `
      <div class="rf-cart-item">
        <span class="rf-cart-item-num">${n}</span>
        <span class="rf-cart-item-price">${fmtBRL(PRICE_PER_QUOTA)}</span>
        <button class="rf-cart-item-remove" onclick="removeFromCart(${n})">×</button>
      </div>
    `).join("");
  } else {
    const preview = nums.slice(0, 8).join(", ");
    const rest = count - 8;
    itemsEl.innerHTML = `
      <div class="rf-cart-bulk">
        <div class="rf-cart-bulk-nums">${preview}<span class="rf-cart-bulk-more"> e mais ${rest.toLocaleString("pt-BR")}</span></div>
        <div class="rf-cart-bulk-count">${count.toLocaleString("pt-BR")} números selecionados</div>
      </div>
    `;
  }

  $("cartTotal").style.display = "flex";
  $("cartTotalValue").textContent = fmtBRL(total);
  $("btnCheckout").disabled = false;
  syncMobileCartVisibility(count, total);
  if (count > state.lastCartCount) {
    pulseMobileCartFab();
  }
  state.lastCartCount = count;
}

window.removeFromCart = function(num) {
  state.selected.delete(num);
  renderGrid();
  updateCart();
};

// ── Quick Buy ─────────────────────────────────────────────────────────────
function setQuickQty(n) {
  const input = $("quickQty");
  input.value = n;
  // Highlight active shortcut button
  document.querySelectorAll(".rf-qty-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.textContent) === n);
  });
  quickBuy(n);
}

function quickBuy(forceQty) {
  const requestedQty = typeof forceQty === "number"
    ? forceQty
    : parseInt($("quickQty").value, 10) || 1;
  const qty = Math.min(requestedQty, MAX_PER_PERSON);
  if (qty < 1) {
    toast("Informe ao menos 1 número.", "error");
    return;
  }
  const available = state.quotas.filter(q => q.status === "available" && !state.selected.has(q.number));
  if (!available.length) {
    toast("Nenhum número disponível.", "error");
    return;
  }
  // Shuffle and pick
  const shuffled = available.slice().sort(() => Math.random() - 0.5);
  const remaining = MAX_PER_PERSON - state.selected.size;
  const toAdd = Math.min(qty, remaining, shuffled.length);
  for (let i = 0; i < toAdd; i++) {
    state.selected.add(shuffled[i].number);
  }
  renderGrid();
  updateCart();
  toast(`${toAdd} número(s) selecionado(s) aleatoriamente!`, "success");
}

// ── Filter tabs ───────────────────────────────────────────────────────────
const FILTER_LABELS = {
  all: "Todos", available: "Livres", reserved: "Reservados",
  paid: "Pagos", unpaid: "Não pagos",
};

function setFilter(status) {
  state.filterStatus = status;
  state.compactPage = 0;
  if (status === "all") {
    state.autoFocusedAllPage = false;
  }
  document.querySelectorAll(".rf-ftab").forEach(btn => {
    btn.classList.toggle("active", btn.id === "ftab-" + status);
  });
  renderGrid();
}

function updateFilterCounts() {
  Object.entries(FILTER_LABELS).forEach(([key, label]) => {
    const el = $("ftab-" + key);
    if (!el) return;
    el.textContent = label;
  });
}

// ── Checkout Modal ────────────────────────────────────────────────────────
function openCheckout() {
  if (!state.selected.size) return;
  closeMobileCart();
  showStep(1);
  $("modalCheckout").classList.remove("hidden");
}

function closeCheckout() {
  $("modalCheckout").classList.add("hidden");
}

function showStep(n) {
  [1, 2, 3].forEach(i => {
    const el = $(`checkoutStep${i}`);
    if (el) el.classList.toggle("hidden", i !== n);
  });
}

async function confirmCheckout() {
  const name = $("buyerName").value.trim();
  const wa = $("buyerWhatsapp").value.replace(/\D/g, "");
  const email = $("buyerEmail").value.trim();
  const cpf = $("buyerCpf").value.trim();

  const errEl = $("checkoutError");
  errEl.style.display = "none";

  if (!name) { showError("Nome é obrigatório."); return; }
  if (wa.length < 10) { showError("WhatsApp inválido (mínimo 10 dígitos)."); return; }

  showStep(3);

  const numbers = [...state.selected];
  try {
    const data = await apiJson(`/api/v2/raffles/${CAMPAIGN_SLUG}/checkout`, {
      method: "POST",
      body: JSON.stringify({
        numbers,
        buyer: { name, whatsapp: wa, email: email || null, cpf: cpf || null },
      }),
    });

    state.pendingOrder = data;

    // Fill PIX UI
    if (data.qr_code_base64) {
      $("qrCodeImg").src = `data:image/png;base64,${data.qr_code_base64}`;
      $("qrWrap").style.display = "flex";
    } else {
      $("qrWrap").style.display = "none";
    }
    $("pixPayloadInput").value = data.pix_payload || "(Chave PIX não configurada)";
    $("pixAmount").textContent = fmtBRL(data.total);
    $("pixExpires").textContent = data.expires_at
      ? new Date(data.expires_at).toLocaleString("pt-BR")
      : "—";

    $("btnTrackOrder").href = data.tracking_url || `/pedido/${data.token}`;

    // Post-purchase share
    const shareText = encodeURIComponent(`Já garantí meu(s) número(s) no sorteio "${CAMPAIGN_TITLE}"! Participe também: ${BASE_URL}/r/${CAMPAIGN_SLUG}`);
    $("postShareWA").href = `https://api.whatsapp.com/send?text=${shareText}`;
    $("postShareTG").href = `https://t.me/share/url?url=${encodeURIComponent(BASE_URL + "/r/" + CAMPAIGN_SLUG)}&text=${shareText}`;

    // Update grid (reserved numbers)
    data.numbers.forEach(n => {
      const q = state.quotas.find(q => q.number === n);
      if (q) q.status = "reserved";
      state.selected.delete(n);
    });
    renderGrid();
    updateCart();

    showStep(2);
  } catch (e) {
    showStep(1);
    showError(e.message);
  }
}

function showError(msg) {
  const el = $("checkoutError");
  el.textContent = msg;
  el.style.display = "block";
}

function maskCpf(value) {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (!digits) return "";
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

function maskPhoneBr(value) {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (!digits) return "";
  if (digits.length <= 2) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
  if (digits.length <= 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
}

function initBuyerInputMasks() {
  const cpfInput = $("buyerCpf");
  const whatsappInput = $("buyerWhatsapp");

  if (cpfInput) {
    cpfInput.value = maskCpf(cpfInput.value);
    cpfInput.addEventListener("input", () => {
      cpfInput.value = maskCpf(cpfInput.value);
    });
  }

  if (whatsappInput) {
    whatsappInput.value = maskPhoneBr(whatsappInput.value);
    whatsappInput.addEventListener("input", () => {
      whatsappInput.value = maskPhoneBr(whatsappInput.value);
    });
  }
}

// ── Share ─────────────────────────────────────────────────────────────────
function initShareButtons() {
  const url = `${BASE_URL}/r/${CAMPAIGN_SLUG}`;
  const text = encodeURIComponent(`${CAMPAIGN_TITLE} — Participe do sorteio! Números a partir de R$${PRICE_PER_QUOTA.toFixed(2).replace(".", ",")}. Acesse:`);
  const shareUrl = encodeURIComponent(url);

  $("shareWhatsApp").href = `https://api.whatsapp.com/send?text=${text}%20${shareUrl}`;
  $("shareTelegram").href = `https://t.me/share/url?url=${shareUrl}&text=${text}`;
  $("shareTwitter").href = `https://twitter.com/intent/tweet?text=${text}&url=${shareUrl}`;

  $("btnCopyLink").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copiado!", "success");
    } catch {
      toast("Não foi possível copiar. Copie manualmente.", "error");
    }
  });

  $("btnCopyMsg").addEventListener("click", async () => {
    const msg = $("shareMsg").textContent;
    try {
      await navigator.clipboard.writeText(msg);
      toast("Mensagem copiada!", "success");
    } catch {
      toast("Não foi possível copiar.", "error");
    }
  });
}

function copyPix() {
  const payload = $("pixPayloadInput").value;
  navigator.clipboard.writeText(payload)
    .then(() => toast("PIX copiado!", "success"))
    .catch(() => toast("Não foi possível copiar.", "error"));
}

// ── Event Listeners ───────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadRaffle();
  initCountdown();
  initShareButtons();
  initBuyerInputMasks();
  syncMobileCartVisibility(0, 0);
  syncQuickBuyOptions();

  $("btnQuickBuy").addEventListener("click", quickBuy);
  $("btnClearCart").addEventListener("click", () => {
    state.selected.clear();
    renderGrid();
    updateCart();
  });
  $("btnCheckout").addEventListener("click", openCheckout);
  $("btnOpenMobileCart")?.addEventListener("click", () => {
    if ($("rfCart")?.classList.contains("open")) {
      closeMobileCart();
      return;
    }
    openMobileCart();
  });
  $("btnCloseMobileCart")?.addEventListener("click", closeMobileCart);
  $("rfCartBackdrop")?.addEventListener("click", closeMobileCart);
  $("btnCloseCheckout").addEventListener("click", closeCheckout);
  $("btnCancelCheckout").addEventListener("click", closeCheckout);
  $("btnConfirmCheckout").addEventListener("click", confirmCheckout);
  $("btnCopyPix").addEventListener("click", copyPix);

  // Close modal on backdrop click
  $("modalCheckout").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeCheckout();
  });

  // Keyboard
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeCheckout();
  });

  window.addEventListener("resize", () => {
    syncMobileCartVisibility(state.selected.size, state.selected.size * PRICE_PER_QUOTA);
    syncQuickBuyOptions();
  });
});
