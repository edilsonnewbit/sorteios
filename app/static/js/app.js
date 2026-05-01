const state = {
  campaigns: [],
  selected: {},    // campaignId -> Set(numbers)
  quotaMap: {},    // campaignId -> quotas list
  pendingQuotaIds: [],
  filterAvailable: false,
};

// ── Utilities ──────────────────────────────────────────────────────────────

function toast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast' + (type ? ' ' + type : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), 3500);
}

async function apiJson(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}

function fmtBRL(v) {
  return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2 });
}

// ── Modals ─────────────────────────────────────────────────────────────────

const modalCreate = document.getElementById('modalCreate');
const modalQR = document.getElementById('modalQR');

function openModal(el) { el && el.classList.remove('hidden'); }
function closeModal(el) { el && el.classList.add('hidden'); }

document.getElementById('btn-new')?.addEventListener('click', () => openModal(modalCreate));
document.getElementById('btn-close-create')?.addEventListener('click', () => closeModal(modalCreate));
document.getElementById('btn-close-qr')?.addEventListener('click', () => closeModal(modalQR));

// close modal on backdrop click
[modalCreate, modalQR].forEach(m => {
  m?.addEventListener('click', e => { if (e.target === m) closeModal(m); });
});

// ── Campaign create form ────────────────────────────────────────────────────

document.getElementById('createForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const errEl = document.getElementById('createError');
  const submitBtn = document.getElementById('btn-create-submit');
  errEl.style.display = 'none';
  submitBtn.disabled = true;
  submitBtn.textContent = 'Criando...';

  const data = {
    title: f.title.value.trim(),
    goal_amount: parseFloat(f.goal_amount.value),
    price_per_quota: parseFloat(f.price_per_quota.value),
    pix_key: f.pix_key.value.trim() || null,
    draw_date: f.draw_date?.value || null,
  };

  try {
    const created = await apiJson('/api/campaigns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    f.reset();
    closeModal(modalCreate);
    if (created?.slug) {
      window.location.href = `/s/${created.slug}`;
      return;
    }
    loadCampaigns();
  } catch (err) {
    errEl.textContent = 'Erro: ' + err.message;
    errEl.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Criar';
  }
});

// ── Campaign list (index page) ──────────────────────────────────────────────

async function loadCampaigns() {
  const listEl = document.getElementById('list');
  if (!listEl) return;
  try {
    const campaigns = await apiJson('/api/campaigns');
    state.campaigns = campaigns;
    renderCampaignList();
  } catch (err) {
    if (listEl) listEl.innerHTML = '<div class="loading-spinner">Erro ao carregar campanhas.</div>';
  }
}

function renderCampaignList() {
  const list = document.getElementById('list');
  if (!list) return;
  list.innerHTML = '';
  if (!state.campaigns.length) {
    list.innerHTML = '<div class="empty-state">Nenhuma campanha ainda. Crie a primeira!</div>';
    return;
  }
  for (const c of state.campaigns) {
    const total = Math.floor(c.goal_amount / c.price_per_quota);
    const card = document.createElement('div');
    card.className = 'campaign-card';
    const badgeClass = c.status === 'drawn' ? 'badge-drawn' : c.status === 'closed' ? 'badge-closed' : 'badge-active';
    const badgeLabel = c.status === 'drawn' ? 'Sorteado' : c.status === 'closed' ? 'Encerrado' : 'Ativo';
    card.innerHTML = `
      <div class="campaign-header">
        <div>
          <div style="display:flex;align-items:center;gap:8px">
            <strong>${c.title}</strong>
            <span class="${badgeClass}">${badgeLabel}</span>
          </div>
          <div class="campaign-meta">${fmtBRL(c.price_per_quota)}/cota &nbsp;•&nbsp; Meta ${fmtBRL(c.goal_amount)} &nbsp;•&nbsp; ${total} cotas</div>
        </div>
        <a class="btn" href="/s/${c.slug}">Abrir</a>
      </div>`;
    list.appendChild(card);
  }
}

// ── Quota grid (campaign page) ──────────────────────────────────────────────

async function loadQuotas(campaignId) {
  const grid = document.getElementById(`grid-${campaignId}`);
  if (grid) grid.innerHTML = '<div class="loading-spinner">Carregando cotas...</div>';
  try {
    const quotas = await apiJson(`/api/campaigns/${campaignId}/quotas`);
    state.quotaMap[campaignId] = quotas;
    if (!state.selected[campaignId]) state.selected[campaignId] = new Set();
    renderGrid(campaignId, quotas);
    updateProgress(campaignId, quotas);
    if (typeof WINNER_QUOTA_ID !== 'undefined' && WINNER_QUOTA_ID) {
      highlightWinner(campaignId, WINNER_QUOTA_ID, quotas);
    }
  } catch (err) {
    if (grid) grid.innerHTML = '<div class="loading-spinner">Erro ao carregar cotas.</div>';
  }
}

function updateProgress(campaignId, quotas) {
  const wrap = document.getElementById('progressWrap');
  const fill = document.getElementById('progressFill');
  const label = document.getElementById('progressLabel');
  if (!wrap) return;
  const total = quotas.length;
  const reserved = quotas.filter(q => q.reserved_by).length;
  const pct = total > 0 ? Math.round((reserved / total) * 100) : 0;
  wrap.style.display = 'block';
  fill.style.width = pct + '%';
  label.textContent = `${reserved} de ${total} cotas reservadas (${pct}%)`;
}

function highlightWinner(campaignId, winnerQuotaId, quotas) {
  const winnerQuota = quotas.find(q => q.id === winnerQuotaId);
  if (!winnerQuota) return;
  const banner = document.getElementById('winnerBanner');
  if (banner) {
    banner.textContent = `Vencedor: Cota #${winnerQuota.number}${winnerQuota.reserved_by ? ' — ' + winnerQuota.reserved_by : ''}`;
  }
  const grid = document.getElementById(`grid-${campaignId}`);
  if (!grid) return;
  grid.querySelectorAll('button').forEach(btn => {
    if (parseInt(btn.dataset.number) === winnerQuota.number) {
      btn.classList.add('winner-highlight');
    } else {
      btn.style.opacity = '0.3';
    }
  });
}

function renderGrid(campaignId, quotas) {
  const grid = document.getElementById(`grid-${campaignId}`);
  if (!grid) return;
  grid.innerHTML = '';
  const sel = state.selected[campaignId] || new Set();
  const visible = state.filterAvailable ? quotas.filter(q => !q.reserved_by && !q.paid) : quotas;
  for (const q of visible) {
    const btn = document.createElement('button');
    btn.textContent = q.number;
    btn.dataset.number = q.number;
    btn.setAttribute('aria-label', `Cota ${q.number}${q.reserved_by ? ' — reservada' : ''}`);
    btn.setAttribute('aria-pressed', sel.has(q.number) ? 'true' : 'false');
    if (q.paid) {
      btn.classList.add('taken-paid');
      btn.disabled = true;
      btn.title = 'Paga';
    } else if (q.reserved_by) {
      btn.classList.add('taken');
      btn.disabled = true;
      btn.title = `Reservada por ${q.reserved_by}`;
    } else {
      if (sel.has(q.number)) btn.classList.add('selected');
      btn.addEventListener('click', () => toggleSelect(campaignId, q.number));
      btn.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggleSelect(campaignId, q.number); }
      });
    }
    grid.appendChild(btn);
  }
}

function toggleSelect(campaignId, number) {
  const sel = state.selected[campaignId];
  if (sel.has(number)) sel.delete(number); else sel.add(number);
  renderGrid(campaignId, state.quotaMap[campaignId]);
  renderCart(campaignId);
}

function toggleFilter() {
  state.filterAvailable = !state.filterAvailable;
  const btn = document.getElementById('btn-filter');
  if (btn) btn.textContent = state.filterAvailable ? 'Mostrar todas' : 'Mostrar disponíveis';
  const cid = typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID ? CAMPAIGN_ID : null;
  if (cid && state.quotaMap[cid]) renderGrid(cid, state.quotaMap[cid]);
}

// ── Cart ────────────────────────────────────────────────────────────────────

function renderCart(campaignId) {
  const itemsEl = document.getElementById('cartItems');
  const totalEl = document.getElementById('cartTotal');
  const totalValEl = document.getElementById('cartTotalValue');
  if (!itemsEl) return;

  const cid = campaignId || (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID ? String(CAMPAIGN_ID) : null);
  if (!cid) return;

  const sel = state.selected[cid] || new Set();
  const pricePerQuota = typeof PRICE_PER_QUOTA !== 'undefined' ? PRICE_PER_QUOTA : 0;

  if (sel.size === 0) {
    itemsEl.innerHTML = 'Nenhuma cota selecionada';
    if (totalEl) totalEl.style.display = 'none';
    return;
  }

  itemsEl.innerHTML = '';
  let total = 0;
  for (const num of Array.from(sel).sort((a, b) => a - b)) {
    total += pricePerQuota;
    const div = document.createElement('div');
    div.className = 'cart-item';
    div.innerHTML = `<span>Cota #${num}</span><span>${fmtBRL(pricePerQuota)}</span>`;
    itemsEl.appendChild(div);
  }

  if (totalEl && totalValEl) {
    totalEl.style.display = 'block';
    totalValEl.textContent = fmtBRL(total);
  }
}

document.getElementById('btn-clear')?.addEventListener('click', () => {
  const cid = typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID ? String(CAMPAIGN_ID) : null;
  if (cid) state.selected[cid]?.clear();
  const cids = Object.keys(state.quotaMap);
  for (const id of cids) renderGrid(id, state.quotaMap[id]);
  renderCart(cid);
});

// ── Checkout ────────────────────────────────────────────────────────────────

document.getElementById('btn-checkout')?.addEventListener('click', async () => {
  const cid = typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID ? String(CAMPAIGN_ID) : null;
  if (!cid) { toast('Nenhuma campanha selecionada', 'error'); return; }

  const sel = state.selected[cid];
  if (!sel || sel.size === 0) { toast('Selecione ao menos uma cota', 'error'); return; }

  const buyer = prompt('Seu nome completo para a reserva:')?.trim();
  if (!buyer) return;

  const btn = document.getElementById('btn-checkout');
  btn.disabled = true;
  btn.textContent = 'Reservando...';

  const quotaIds = [];
  try {
    for (const num of sel) {
      const form = new FormData();
      form.append('number', num);
      form.append('buyer', buyer);
      const res = await fetch(`/api/campaigns/${cid}/reserve`, { method: 'POST', body: form });
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
        throw new Error(`Cota #${num}: ${detail}`);
      }
      const data = await res.json();
      quotaIds.push(data.quota_id);
    }
  } catch (err) {
    toast('Erro ao reservar: ' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Pagar com PIX';
    await loadQuotas(cid);
    return;
  }

  // generate QR
  btn.textContent = 'Gerando QR...';
  try {
    const form2 = new FormData();
    form2.append('campaign_id', cid);
    form2.append('quota_ids', quotaIds.join(','));
    const qrRes = await fetch('/api/checkout', { method: 'POST', body: form2 });
    if (!qrRes.ok) throw new Error('Falha ao gerar QR PIX');

    const pixPayload = qrRes.headers.get('X-Pix-Payload') || '';
    const amount = qrRes.headers.get('X-Amount') || '';
    const blob = await qrRes.blob();
    const url = URL.createObjectURL(blob);

    document.getElementById('qrArea').innerHTML = `<img src="${url}" alt="QR PIX" />`;
    const payloadInput = document.getElementById('pixPayload');
    const copyWrap = document.getElementById('pixCopyWrap');
    const amountEl = document.getElementById('pixAmount');
    if (payloadInput && pixPayload) {
      payloadInput.value = pixPayload;
      copyWrap.style.display = 'flex';
    }
    if (amountEl && amount) amountEl.textContent = fmtBRL(amount);

    openModal(modalQR);
    state.pendingQuotaIds = quotaIds;
    sel.clear();
    await loadQuotas(cid);
    renderCart(cid);
  } catch (err) {
    toast('Erro ao gerar PIX: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Pagar com PIX';
  }
});

function copyPix() {
  const input = document.getElementById('pixPayload');
  if (!input) return;
  navigator.clipboard.writeText(input.value).then(() => toast('Código PIX copiado!', 'success'));
}

// ── Init ────────────────────────────────────────────────────────────────────

if (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) {
  loadQuotas(CAMPAIGN_ID);
} else {
  loadCampaigns();
}
