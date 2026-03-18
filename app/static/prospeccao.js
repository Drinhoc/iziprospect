/* prospeccao.js — IziLead prospect review queue */

let currentTab = 'pendente';
let currentPage = 1;
const PAGE_SIZE = 50;
let currentBuscaId = null;
let enrichPollInterval = null;
let isSearching = false;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  loadCounts();
  loadProspects();
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function iniciarBusca() {
  if (isSearching) return;

  const segmento = document.getElementById('prosp-segmento').value.trim();
  const cidade = document.getElementById('prosp-cidade').value.trim();
  const limit = parseInt(document.getElementById('prosp-limit').value, 10);
  const fontes = [...document.querySelectorAll('.prosp-fonte-check input:checked')]
    .map(cb => cb.value);

  if (!segmento) { alert('Digite o tipo de negócio.'); return; }
  if (!cidade) { alert('Digite a cidade.'); return; }
  if (fontes.length === 0) { alert('Selecione ao menos uma fonte.'); return; }

  isSearching = true;
  const btn = document.getElementById('btn-buscar');
  btn.disabled = true;
  btn.textContent = 'Buscando…';

  stopEnrichPoll();

  try {
    const res = await fetch('/api/prospeccao/buscar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segmento, cidade, limit, fontes }),
    });

    if (!res.ok) {
      const err = await res.json();
      alert('Erro: ' + (err.detail || res.statusText));
      return;
    }

    const data = await res.json();
    currentBuscaId = data.busca_id;

    const info = document.getElementById('prosp-busca-info');
    info.textContent = data.message;
    info.classList.remove('hidden');

    // Show enrichment progress
    showEnrichStatus('Enriquecendo WhatsApp…');
    startEnrichPoll(data.busca_id);

    currentTab = 'pendente';
    currentPage = 1;
    setActiveTab('pendente');
    await loadCounts();
    await loadProspects();

  } catch (e) {
    alert('Erro de conexão: ' + e.message);
  } finally {
    isSearching = false;
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Buscar Leads';
  }
}

// ---------------------------------------------------------------------------
// Enrichment poll
// ---------------------------------------------------------------------------

function showEnrichStatus(text) {
  const el = document.getElementById('prosp-enrich-status');
  document.getElementById('prosp-enrich-text').textContent = text;
  el.classList.remove('hidden');
}

function hideEnrichStatus() {
  document.getElementById('prosp-enrich-status').classList.add('hidden');
}

function startEnrichPoll(busca_id) {
  stopEnrichPoll();
  enrichPollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/prospeccao/status/${busca_id}`);
      const data = await res.json();
      const { total, enriquecidos, pendentes } = data;

      if (total > 0) {
        showEnrichStatus(`Enriquecendo… ${enriquecidos}/${total}`);
      }

      // Reload list to show updated WhatsApp badges
      await loadProspects(false);
      await loadCounts();

      if (pendentes === 0) {
        stopEnrichPoll();
        hideEnrichStatus();
        await loadProspects(false);
      }
    } catch {
      stopEnrichPoll();
    }
  }, 3000);
}

function stopEnrichPoll() {
  if (enrichPollInterval) {
    clearInterval(enrichPollInterval);
    enrichPollInterval = null;
  }
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function switchTab(tab, el) {
  currentTab = tab;
  currentPage = 1;
  setActiveTab(tab);
  loadProspects();

  // Show/hide tab-specific actions
  document.getElementById('btn-aprovar-lote').classList.toggle('hidden', tab !== 'pendente');
  document.getElementById('btn-reenriquecer').classList.toggle('hidden', tab !== 'pendente');
  document.getElementById('btn-limpar-desc').classList.toggle('hidden', tab !== 'descartado');
}

function setActiveTab(tab) {
  document.querySelectorAll('.prosp-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tab);
  });
}

// ---------------------------------------------------------------------------
// Load prospects
// ---------------------------------------------------------------------------

async function loadProspects(showLoader = true) {
  if (showLoader) {
    document.getElementById('prosp-loading').classList.remove('hidden');
    document.getElementById('prosp-list').innerHTML = '';
    document.getElementById('prosp-empty').classList.add('hidden');
    document.getElementById('prosp-pagination').classList.add('hidden');
  }

  const params = new URLSearchParams({
    status_revisao: currentTab,
    page: currentPage,
    page_size: PAGE_SIZE,
  });
  if (currentBuscaId && currentTab === 'pendente') {
    // don't filter by busca_id so we see all pending, not just last search
  }

  try {
    const res = await fetch('/api/prospeccao/fila?' + params);
    const data = await res.json();
    renderProspects(data);
  } catch (e) {
    console.error('loadProspects error:', e);
  } finally {
    if (showLoader) {
      document.getElementById('prosp-loading').classList.add('hidden');
    }
  }
}

function renderProspects(data) {
  const list = document.getElementById('prosp-list');
  const empty = document.getElementById('prosp-empty');
  const pagination = document.getElementById('prosp-pagination');

  if (!data.prospects || data.prospects.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    const emptyTexts = {
      pendente: 'Nenhum prospect pendente. Faça uma busca acima.',
      aprovado: 'Nenhum prospect aprovado ainda.',
      descartado: 'Nenhum prospect descartado.',
    };
    document.getElementById('prosp-empty-text').textContent = emptyTexts[currentTab] || 'Nenhum resultado.';
    pagination.classList.add('hidden');
    return;
  }

  empty.classList.add('hidden');
  list.innerHTML = data.prospects.map(renderCard).join('');

  // Pagination
  const totalPages = Math.ceil(data.total / PAGE_SIZE);
  if (totalPages > 1) {
    pagination.classList.remove('hidden');
    document.getElementById('prosp-page-info').textContent = `Página ${currentPage} de ${totalPages}`;
    document.getElementById('prosp-btn-prev').disabled = currentPage <= 1;
    document.getElementById('prosp-btn-next').disabled = currentPage >= totalPages;
  } else {
    pagination.classList.add('hidden');
  }

  document.getElementById('prosp-total-label').textContent =
    data.total > 0 ? `${data.total} prospects` : '';
}

function renderCard(p) {
  const hasWA = p.whatsapp && p.whatsapp.trim();
  const hasPhone = p.telefone && p.telefone.trim();
  const isApproved = p.status_revisao === 'aprovado';
  const isDiscarded = p.status_revisao === 'descartado';
  const enriching = p.enriquecido === 0 && p.website;

  const waBadge = hasWA
    ? `<span class="badge badge-wa">💬 ${escHtml(p.whatsapp)}</span>`
    : hasPhone
      ? `<span class="badge badge-phone">📞 ${escHtml(p.telefone)}</span>`
      : enriching
        ? `<span class="badge badge-enriching">⏳ buscando WA…</span>`
        : `<span class="badge badge-no-contact">— sem contato</span>`;

  const fonteBadge = `<span class="badge badge-fonte">${escHtml(p.fonte || '')}</span>`;

  const websiteLink = p.website
    ? `<a href="${escHtml(p.website)}" target="_blank" rel="noopener" class="prosp-link">🌐 ${shortUrl(p.website)}</a>`
    : '';

  const mapsLink = p.link_maps
    ? `<a href="${escHtml(p.link_maps)}" target="_blank" rel="noopener" class="prosp-link-maps">↗ Maps</a>`
    : '';

  const rating = p.rating ? `<span class="prosp-rating">★ ${escHtml(p.rating)}</span>` : '';

  let actions = '';
  if (!isApproved && !isDiscarded) {
    actions = `
      <div class="prosp-card-actions">
        <button class="btn-aprovar" onclick="aprovarUm(${p.id}, this)">Aprovar →</button>
        <button class="btn-descartar" onclick="descartarUm(${p.id}, this)">✕</button>
      </div>`;
  } else if (isApproved) {
    const leadLink = p.lead_id_aprovado
      ? `<a href="/leads" class="prosp-lead-link">Ver lead ${escHtml(p.lead_id_aprovado)}</a>`
      : '';
    actions = `<div class="prosp-card-actions"><span class="badge badge-aprovado">✓ Aprovado</span>${leadLink}</div>`;
  } else {
    actions = `<div class="prosp-card-actions"><span class="badge badge-descartado">✕ Descartado</span></div>`;
  }

  return `
    <div class="prospect-card" id="prospect-${p.id}">
      <div class="prosp-card-header">
        <div class="prosp-card-nome">${escHtml(p.nome)}</div>
        <div class="prosp-card-meta">
          ${fonteBadge}
          <span class="prosp-cidade">${escHtml(p.cidade)}</span>
          ${rating}
        </div>
      </div>
      <div class="prosp-card-contacts">
        ${waBadge}
        ${websiteLink}
        ${mapsLink}
      </div>
      ${p.instagram ? `<div class="prosp-card-instagram"><a href="${escHtml(p.instagram)}" target="_blank" rel="noopener" class="prosp-link">📸 Instagram</a></div>` : ''}
      ${actions}
    </div>`;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function aprovarUm(id, btn) {
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const res = await fetch(`/api/prospeccao/${id}/aprovar`, { method: 'PUT' });
    if (!res.ok) { alert('Erro ao aprovar.'); btn.disabled = false; btn.textContent = 'Aprovar →'; return; }
    const data = await res.json();
    const card = document.getElementById(`prospect-${id}`);
    if (card) card.classList.add('prosp-card--removing');
    setTimeout(async () => {
      await loadCounts();
      await loadProspects(false);
    }, 350);
  } catch (e) {
    alert('Erro: ' + e.message);
    btn.disabled = false;
    btn.textContent = 'Aprovar →';
  }
}

async function descartarUm(id, btn) {
  btn.disabled = true;
  try {
    await fetch(`/api/prospeccao/${id}/descartar`, { method: 'PUT' });
    const card = document.getElementById(`prospect-${id}`);
    if (card) card.classList.add('prosp-card--removing');
    setTimeout(async () => {
      await loadCounts();
      await loadProspects(false);
    }, 350);
  } catch (e) {
    alert('Erro: ' + e.message);
    btn.disabled = false;
  }
}

async function aprovarComWhatsApp() {
  if (!currentBuscaId) {
    alert('Faça uma busca primeiro para usar esta função.');
    return;
  }
  const btn = document.getElementById('btn-aprovar-lote');
  btn.disabled = true;
  btn.textContent = 'Aprovando…';
  try {
    const res = await fetch('/api/prospeccao/aprovar-lote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apenas_com_whatsapp: true, busca_id: currentBuscaId }),
    });
    const data = await res.json();
    alert(`${data.aprovados} lead(s) aprovado(s)!`);
    await loadCounts();
    await loadProspects();
  } catch (e) {
    alert('Erro: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Aprovar c/ WhatsApp';
  }
}

async function reEnriquecer() {
  const btn = document.getElementById('btn-reenriquecer');
  btn.disabled = true;
  btn.textContent = 'Varrendo…';
  try {
    const res = await fetch('/api/prospeccao/re-enriquecer', { method: 'POST' });
    const data = await res.json();
    alert('Varredura iniciada! Todos os leads com status "novo" e sem WhatsApp serão reprocessados em background.\n\nAguarde alguns minutos e verifique os leads.');
  } catch (e) {
    alert('Erro: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Buscar WhatsApp nos leads novos';
  }
}

async function limparDescartados() {
  if (!confirm('Remover todos os prospects descartados?')) return;
  try {
    const res = await fetch('/api/prospeccao/fila/descartados', { method: 'DELETE' });
    const data = await res.json();
    alert(`${data.removidos} removidos.`);
    await loadCounts();
    await loadProspects();
  } catch (e) {
    alert('Erro: ' + e.message);
  }
}

// ---------------------------------------------------------------------------
// Counts
// ---------------------------------------------------------------------------

async function loadCounts() {
  try {
    const res = await fetch('/api/prospeccao/contadores');
    const data = await res.json();
    document.getElementById('count-pendente').textContent = data.pendente || 0;
    document.getElementById('count-aprovado').textContent = data.aprovado || 0;
    document.getElementById('count-descartado').textContent = data.descartado || 0;
  } catch { /* silently ignore */ }
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

async function prospChangePage(delta) {
  currentPage = Math.max(1, currentPage + delta);
  await loadProspects();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function shortUrl(url) {
  try {
    const u = new URL(url.startsWith('http') ? url : 'https://' + url);
    return u.hostname.replace(/^www\./, '');
  } catch {
    return url.substring(0, 30);
  }
}
