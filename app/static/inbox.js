/* inbox.js — MVP 2.0: Inbox WhatsApp */

let currentStatus = 'aberto';
let currentPage = 1;
const PAGE_SIZE = 20;
let searchTimeout = null;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadConversas();
  setInterval(loadStats, 30000);
});

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

async function loadStats() {
  try {
    const d = await fetch('/api/inbox/stats').then(r => r.json());
    document.getElementById('ist-abertas').textContent    = d.abertas    ?? '—';
    document.getElementById('ist-urgentes').textContent   = d.urgentes   ?? '—';
    document.getElementById('ist-nao-lidas').textContent  = d.total_nao_lidas ?? '—';
    document.getElementById('ist-resolvidas').textContent = d.resolvidas ?? '—';

    const tabCount = document.getElementById('tab-count-aberto');
    if (tabCount) tabCount.textContent = d.abertas > 0 ? d.abertas : '';

    const subtitle = document.getElementById('inbox-subtitle');
    if (subtitle) {
      const nl = d.total_nao_lidas || 0;
      subtitle.textContent = nl > 0 ? `${nl} mensagem${nl > 1 ? 's' : ''} não lida${nl > 1 ? 's' : ''}` : '';
    }
  } catch { /* silencia */ }
}

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

function setStatusFilter(status, el) {
  currentStatus = status;
  currentPage = 1;
  document.querySelectorAll('.inbox-tab').forEach(t => t.classList.toggle('active', t.dataset.status === status));
  loadConversas();
}

function applyFilters() {
  currentPage = 1;
  loadConversas();
}

function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(applyFilters, 400);
}

// ---------------------------------------------------------------------------
// Carregar lista
// ---------------------------------------------------------------------------

async function loadConversas(showLoader = true) {
  if (showLoader) {
    document.getElementById('inbox-loading').classList.remove('hidden');
    document.getElementById('inbox-list').innerHTML = '';
    document.getElementById('inbox-empty').classList.add('hidden');
    document.getElementById('inbox-pagination').classList.add('hidden');
  }

  const cat  = document.getElementById('filter-categoria').value;
  const prio = document.getElementById('filter-prioridade').value;
  const q    = document.getElementById('inbox-search').value.trim();

  const params = new URLSearchParams({ status: currentStatus, page: currentPage, page_size: PAGE_SIZE });
  if (cat)  params.set('categoria', cat);
  if (prio) params.set('prioridade', prio);
  if (q)    params.set('search', q);

  try {
    const data = await fetch('/api/inbox/conversas?' + params).then(r => r.json());
    renderConversas(data);
  } catch (e) {
    console.error('loadConversas error:', e);
  } finally {
    if (showLoader) document.getElementById('inbox-loading').classList.add('hidden');
  }
}

function renderConversas(data) {
  const list       = document.getElementById('inbox-list');
  const empty      = document.getElementById('inbox-empty');
  const pagination = document.getElementById('inbox-pagination');

  if (!data.conversas || data.conversas.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    const msg = {
      aberto:    'Nenhuma conversa aberta.',
      resolvido: 'Nenhuma conversa resolvida.',
      arquivado: 'Nenhuma conversa arquivada.',
      todas:     'Nenhuma conversa registrada ainda.',
    };
    document.getElementById('inbox-empty-text').textContent = msg[currentStatus] || 'Nenhuma conversa encontrada.';
    pagination.classList.add('hidden');
    return;
  }

  empty.classList.add('hidden');
  list.innerHTML = data.conversas.map(renderCard).join('');

  const totalPages = Math.ceil(data.total / PAGE_SIZE);
  if (totalPages > 1) {
    pagination.classList.remove('hidden');
    document.getElementById('inbox-page-info').textContent = `Página ${currentPage} de ${totalPages}`;
    document.getElementById('inbox-btn-prev').disabled = currentPage <= 1;
    document.getElementById('inbox-btn-next').disabled = currentPage >= totalPages;
  } else {
    pagination.classList.add('hidden');
  }
}

function renderCard(c) {
  const nome     = escHtml(c.nome_contato || c.numero || 'Desconhecido');
  const numero   = escHtml(c.numero || '');
  const resumo   = escHtml(c.resumo_ia || 'Sem análise ainda…');
  const naoLidas = c.nao_lidas > 0
    ? `<span class="inbox-card-unread">${c.nao_lidas}</span>`
    : '';
  const prioClass = `inbox-prio--${c.prioridade || 'normal'}`;
  const catBadge  = c.categoria && c.categoria !== 'outro'
    ? `<span class="inbox-cat-badge inbox-cat--${c.categoria}">${escHtml(c.categoria)}</span>`
    : '';
  const tempo = c.ultimo_msg_em ? timeAgo(c.ultimo_msg_em) : '';
  const statusBadge = c.status !== 'aberto'
    ? `<span class="inbox-status-badge inbox-status--${c.status}">${c.status}</span>`
    : '';

  return `
    <a class="inbox-card ${prioClass}" href="/inbox/${c.id}">
      <div class="inbox-card-avatar">
        ${avatarLetters(c.nome_contato || c.numero)}
      </div>
      <div class="inbox-card-body">
        <div class="inbox-card-top">
          <span class="inbox-card-nome">${nome}</span>
          <span class="inbox-card-time">${tempo}</span>
        </div>
        <div class="inbox-card-preview">${resumo}</div>
        <div class="inbox-card-meta">
          ${catBadge}
          ${statusBadge}
          <span class="inbox-card-msgs">${c.total_mensagens} msg${c.total_mensagens !== 1 ? 's' : ''}</span>
        </div>
      </div>
      ${naoLidas}
    </a>`;
}

// ---------------------------------------------------------------------------
// Paginação
// ---------------------------------------------------------------------------

async function inboxChangePage(delta) {
  currentPage = Math.max(1, currentPage + delta);
  await loadConversas();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function avatarLetters(name) {
  const s = (name || '?').trim();
  const digits = s.replace(/\D/g, '');
  if (digits.length > 4) return digits.slice(-4);
  const words = s.split(/\s+/);
  return words.slice(0, 2).map(w => w[0].toUpperCase()).join('');
}

function timeAgo(isoStr) {
  try {
    const diff = Date.now() - new Date(isoStr).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'agora';
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h`;
    const d = Math.floor(h / 24);
    return `${d}d`;
  } catch { return ''; }
}
