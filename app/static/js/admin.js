function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function toast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast' + (type ? ' ' + type : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), 4000);
}

async function startDraw(campaignId, title) {
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-card" style="max-width:520px">
      <h3>Sorteando — ${title}</h3>
      <p class="muted" style="font-size:13px;margin-bottom:12px">Pressione "Executar sorteio" para sortear o vencedor entre as cotas elegíveis.</p>
      <div id="drawSpinner" style="display:flex;flex-wrap:wrap;gap:6px;max-height:300px;overflow-y:auto;justify-content:center;padding:4px"></div>
      <div id="drawStatus" style="text-align:center;margin:12px 0;min-height:24px;color:#9aa4b2;font-size:13px"></div>
      <div style="display:flex;gap:8px;justify-content:center;margin-top:4px">
        <button id="btn-execute" class="btn primary">Executar sorteio</button>
        <button id="btn-close-draw" class="btn">Fechar</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  const spinner = modal.querySelector('#drawSpinner');
  const statusEl = modal.querySelector('#drawStatus');
  const btnExecute = modal.querySelector('#btn-execute');
  const btnClose = modal.querySelector('#btn-close-draw');

  btnClose.addEventListener('click', () => modal.remove());
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });

  // load quotas
  statusEl.textContent = 'Carregando cotas...';
  let quotas = [];
  try {
    const res = await fetch(`/api/campaigns/${campaignId}/quotas`);
    quotas = await res.json();
  } catch (_) {
    statusEl.textContent = 'Erro ao carregar cotas.';
    return;
  }

  const eligible = quotas.filter(q => q.paid);
  const reserved = quotas.filter(q => q.reserved_by && !q.paid);
  const pool = eligible.length > 0 ? eligible : reserved.length > 0 ? reserved : quotas;

  const poolLabel = eligible.length > 0
    ? `${eligible.length} cotas pagas`
    : reserved.length > 0
      ? `${reserved.length} cotas reservadas`
      : `${quotas.length} cotas totais`;
  statusEl.textContent = `Pool do sorteio: ${poolLabel}`;

  // render quota boxes
  const boxMap = {};
  for (const q of quotas) {
    const b = document.createElement('div');
    b.textContent = q.number;
    b.dataset.number = q.number;
    const inPool = pool.some(p => p.id === q.id);
    b.style.cssText = [
      'width:48px', 'height:48px', 'display:flex', 'align-items:center', 'justify-content:center',
      'border-radius:8px', 'font-weight:700', 'font-size:13px', 'transition:all .1s',
      inPool
        ? 'background:linear-gradient(135deg,#7c3aed,#06b6d4);color:white'
        : 'background:rgba(255,255,255,0.02);color:#3d4a5c',
    ].join(';');
    spinner.appendChild(b);
    boxMap[q.number] = b;
  }

  let running = false;
  btnExecute.addEventListener('click', async () => {
    if (running) return;
    running = true;
    btnExecute.disabled = true;
    btnExecute.textContent = 'Sorteando...';
    statusEl.textContent = '';

    const poolBoxes = pool.map(q => boxMap[q.number]).filter(Boolean);
    const rounds = 40;

    // animation
    for (let i = 0; i < rounds; i++) {
      poolBoxes.forEach(b => { b.style.transform = 'scale(1)'; b.style.boxShadow = 'none'; });
      const pick = poolBoxes[Math.floor(Math.random() * poolBoxes.length)];
      if (pick) {
        pick.style.transform = 'scale(1.15)';
        pick.style.boxShadow = '0 0 24px rgba(124,58,237,0.6)';
      }
      await sleep(60 + i * 4);
    }
    poolBoxes.forEach(b => { b.style.transform = 'scale(1)'; b.style.boxShadow = 'none'; });

    // call server
    try {
      const res = await fetch(`/admin/draw/${campaignId}`, { method: 'POST' });
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
        throw new Error(detail);
      }
      const data = await res.json();

      // highlight winner
      Object.values(boxMap).forEach(b => { b.style.opacity = '0.25'; });
      const winBox = boxMap[data.number];
      if (winBox) {
        winBox.style.opacity = '1';
        winBox.style.transform = 'scale(1.3)';
        winBox.style.boxShadow = '0 0 40px rgba(245,158,11,0.5)';
        winBox.style.background = 'linear-gradient(135deg,#f59e0b,#ef4444)';
        winBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }

      const name = data.reserved_by ? ` — ${data.reserved_by}` : '';
      statusEl.innerHTML = `<strong style="color:#f59e0b;font-size:15px">Vencedor: Cota #${data.number}${name}</strong>`;
      toast(`Vencedor sorteado: Cota #${data.number}${name}`, 'success');

      // update badge on dashboard card
      const cardBadges = document.querySelectorAll(`[onclick*="startDraw(${campaignId},"]`);
      cardBadges.forEach(btn => {
        const card = btn.closest('.campaign-card');
        const badge = card?.querySelector('.badge-active, .badge-drawn');
        if (badge) { badge.className = 'badge-drawn'; badge.textContent = 'Sorteado'; }
        btn.textContent = 'Ressortear';
      });
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#f87171">Erro: ${err.message}</span>`;
      btnExecute.disabled = false;
      btnExecute.textContent = 'Tentar novamente';
      running = false;
    }
  });
}
