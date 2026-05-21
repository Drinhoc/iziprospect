/* dashboard.js — MVP 2.0: inbox-first dashboard */

// ---------------------------------------------------------------------------
// Paleta de cores
// ---------------------------------------------------------------------------

const CAT_COLORS = {
  suporte:    '#3b82f6',
  vendas:     '#10b981',
  informacao: '#f59e0b',
  spam:       '#ef4444',
  outro:      '#9ca3af',
};

const CAT_LABELS = {
  suporte:    'Suporte',
  vendas:     'Vendas',
  informacao: 'Informação',
  spam:       'Spam',
  outro:      'Outro',
};

const STATUS_COLORS = {
  'novo':             '#9ca3af',
  '1º contato':       '#06b6d4',
  'qualificado':      '#8b5cf6',
  'negociando':       '#f97316',
  'em espera':        '#eab308',
  'sem resposta':     '#4b5563',
  'fechado':          '#10b981',
  'perdido':          '#ef4444',
  'contato inválido': '#374151',
};

const PRIO_COLORS = {
  urgente: '#dc2626',
  alta:    '#f59e0b',
  normal:  '#6b7280',
  baixa:   '#10b981',
};

const VOL_COLOR = '#1a56db';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'agora';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function avatarLetters(name) {
  const s = (name || '?').trim();
  const digits = s.replace(/\D/g, '');
  if (digits.length > 4) return digits.slice(-4);
  return s.split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join('');
}

function buildBars(containerId, entries, colorMap, fallbackColors) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!entries || entries.length === 0) {
    el.innerHTML = '<span class="chart-empty">Sem dados ainda</span>';
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v));
  el.innerHTML = entries.map(([key, val], i) => {
    const pct   = max > 0 ? Math.round((val / max) * 100) : 0;
    const color = colorMap[key] || (fallbackColors && fallbackColors[i % fallbackColors.length]) || '#6b7280';
    const label = CAT_LABELS[key] || key;
    return `
      <div class="bar-item">
        <div class="bar-label-row">
          <strong>${escHtml(label)}</strong>
          <span>${val}</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Seção "Atenção agora"
// ---------------------------------------------------------------------------

function renderAtencao(urgentes) {
  const section = document.getElementById('atencao-section');
  const list    = document.getElementById('atencao-list');

  if (!urgentes || urgentes.length === 0) {
    section.classList.add('hidden');
    return;
  }

  section.classList.remove('hidden');
  list.innerHTML = urgentes.map(c => {
    const nome  = escHtml(c.nome_contato || c.numero || 'Desconhecido');
    const resumo = escHtml((c.resumo_ia || 'Sem análise ainda').slice(0, 90));
    const prio  = c.prioridade || 'normal';
    const cat   = c.categoria || 'outro';
    const nl    = c.nao_lidas || 0;
    const tempo = timeAgo(c.ultimo_msg_em);
    const prioColor = PRIO_COLORS[prio] || '#6b7280';

    return `
      <a class="atencao-card" href="/inbox/${c.id}">
        <div class="atencao-avatar" style="background:${prioColor}">${avatarLetters(c.nome_contato || c.numero)}</div>
        <div class="atencao-body">
          <div class="atencao-top">
            <span class="atencao-nome">${nome}</span>
            <span class="atencao-badges">
              <span class="atencao-prio-badge" style="background:${prioColor}20;color:${prioColor}">${prio}</span>
              <span class="atencao-cat-badge">${CAT_LABELS[cat] || cat}</span>
            </span>
          </div>
          <div class="atencao-resumo">${resumo}${c.resumo_ia && c.resumo_ia.length > 90 ? '…' : ''}</div>
        </div>
        <div class="atencao-meta">
          ${nl > 0 ? `<span class="atencao-nl">${nl}</span>` : ''}
          <span class="atencao-tempo">${tempo}</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </a>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Lista "Aguardando resposta"
// ---------------------------------------------------------------------------

function renderSemResposta(list_data) {
  const el = document.getElementById('list-sem-resposta');
  if (!el) return;

  if (!list_data || list_data.length === 0) {
    el.innerHTML = '<li><span class="ml-empty">Nenhuma conversa aguardando resposta 🎉</span></li>';
    return;
  }

  el.innerHTML = list_data.map(c => {
    const nome  = escHtml(c.nome_contato || c.numero || 'Desconhecido');
    const nl    = c.nao_lidas || 0;
    const tempo = timeAgo(c.ultimo_msg_em);
    return `
      <li onclick="window.location='/inbox/${c.id}'" style="cursor:pointer">
        <span class="ml-name">${nome}</span>
        <span class="ml-date">
          ${nl > 0 ? `<span class="ml-nl">${nl}</span>` : ''}
          ${tempo}
        </span>
      </li>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// CRM resumo
// ---------------------------------------------------------------------------

function renderCrmResumo(crm) {
  const el = document.getElementById('crm-resumo-grid');
  if (!el || !crm) return;

  const items = [
    { label: 'Leads ativos',     value: crm.leads_ativos   ?? '—', icon: '👤' },
    { label: 'Follow-ups hoje',  value: crm.followups_hoje ?? '—', icon: '📅' },
    { label: 'Novos na semana',  value: crm.criados_semana ?? '—', icon: '✨' },
  ];

  el.innerHTML = items.map(it => `
    <div class="crm-resumo-item">
      <span class="crm-resumo-icon">${it.icon}</span>
      <span class="crm-resumo-value">${it.value}</span>
      <span class="crm-resumo-label">${it.label}</span>
    </div>`).join('');
}

// ---------------------------------------------------------------------------
// Chart volume 7 dias
// ---------------------------------------------------------------------------

function buildVolume7d(data) {
  const el = document.getElementById('chart-volume7d');
  if (!el) return;

  if (!data || data.length === 0) {
    el.innerHTML = '<span class="chart-empty">Sem dados nos últimos 7 dias</span>';
    return;
  }

  const max = Math.max(...data.map(d => d.total));
  el.innerHTML = data.map(d => {
    const pct   = max > 0 ? Math.round((d.total / max) * 100) : 0;
    const label = d.dia ? d.dia.slice(5).replace('-', '/') : '?';
    return `
      <div class="bar-item">
        <div class="bar-label-row">
          <strong>${label}</strong>
          <span>${d.total}</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%;background:${VOL_COLOR}"></div>
        </div>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Carregamento principal
// ---------------------------------------------------------------------------

async function loadDashboard() {
  try {
    const d = await fetch('/api/inbox/dashboard').then(r => r.json());

    // Stat cards
    const s = d.stats || {};
    document.getElementById('stat-abertas').textContent    = s.abertas    ?? '—';
    document.getElementById('stat-urgentes').textContent   = s.urgentes   ?? '—';
    document.getElementById('stat-nao-lidas').textContent  = s.total_nao_lidas ?? '—';
    document.getElementById('stat-resolvidas').textContent = s.resolvidas_hoje  ?? '—';

    // Atenção agora
    renderAtencao(d.urgentes || []);

    // Chart: categorias
    const catEntries = Object.entries(s.por_categoria || {}).sort((a, b) => b[1] - a[1]);
    buildBars('chart-categorias', catEntries, CAT_COLORS, null);

    // Chart: volume 7 dias
    buildVolume7d(s.volume_7d || []);

    // Chart: pipeline CRM
    const crm = d.crm_resumo || {};
    const statusEntries = Object.entries(crm.by_status || {}).sort((a, b) => b[1] - a[1]).slice(0, 6);
    buildBars('chart-status', statusEntries, STATUS_COLORS, null);

    // Lista sem resposta
    renderSemResposta(d.sem_resposta || []);

    // CRM resumo
    renderCrmResumo(crm);

    // Timestamp
    document.getElementById('last-update').textContent =
      'Atualizado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

loadDashboard();
setInterval(loadDashboard, 60_000);  // Refresh a cada 1 minuto
