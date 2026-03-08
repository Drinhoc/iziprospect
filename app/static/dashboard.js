/* Dashboard JS */

const STATUS_ORDER = [
  'novo', 'em contato', 'qualificado', 'proposta enviada', 'negociando', 'fechado', 'perdido', 'sem resposta'
];

const STATUS_COLORS = {
  'novo':             '#9ca3af',
  'em contato':       '#3b82f6',
  'qualificado':      '#8b5cf6',
  'proposta enviada': '#f59e0b',
  'negociando':       '#f97316',
  'fechado':          '#10b981',
  'perdido':          '#ef4444',
  'sem resposta':     '#4b5563',
};

const SEGMENTO_COLORS = ['#3b82f6','#8b5cf6','#f59e0b','#10b981','#f97316','#6366f1','#14b8a6'];
const PRIO_COLORS = { alta: '#ef4444', media: '#f59e0b', baixa: '#10b981' };

function fmtDate(s) {
  if (!s) return '—';
  return s.slice(0, 10).split('-').reverse().join('/');
}

function buildBars(container, data, colorMap, maxVal) {
  container.innerHTML = '';
  if (!data || data.length === 0) {
    container.innerHTML = '<span style="color:#9ca3af;font-size:.82rem">Sem dados</span>';
    return;
  }
  const max = maxVal || Math.max(...Object.values(data));
  data.forEach(([key, val], i) => {
    const pct = max > 0 ? Math.round((val / max) * 100) : 0;
    const color = colorMap[key] || SEGMENTO_COLORS[i % SEGMENTO_COLORS.length];
    const item = document.createElement('div');
    item.className = 'bar-item';
    item.innerHTML = `
      <div class="bar-label-row">
        <strong>${key}</strong>
        <span>${val}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
      </div>`;
    container.appendChild(item);
  });
}

async function loadDashboard() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('API error');
    const d = await res.json();

    // Cards
    document.getElementById('stat-ativos').textContent = d.total_ativos;
    document.getElementById('stat-vencidos').textContent = d.followups_vencidos;
    document.getElementById('stat-hoje').textContent = d.followups_hoje;
    document.getElementById('stat-semana').textContent = d.criados_semana;

    // Pipeline chart — ordered
    const statusData = STATUS_ORDER
      .filter(s => d.by_status[s])
      .map(s => [s, d.by_status[s]]);
    // Add any status not in order
    Object.entries(d.by_status).forEach(([k, v]) => {
      if (!STATUS_ORDER.includes(k)) statusData.push([k, v]);
    });
    buildBars(document.getElementById('chart-status'), statusData, STATUS_COLORS);

    // Segmento chart
    const segData = Object.entries(d.by_segmento).sort((a, b) => b[1] - a[1]);
    buildBars(document.getElementById('chart-segmento'), segData, {});

    // Prioridade chart
    const prioData = Object.entries(d.by_prioridade).sort((a, b) => b[1] - a[1]);
    buildBars(document.getElementById('chart-prioridade'), prioData, PRIO_COLORS);

    // Follow-ups list
    const fuList = document.getElementById('list-followups');
    fuList.innerHTML = '';
    if (d.proximos_followups.length === 0) {
      fuList.innerHTML = '<li><span class="ml-empty">Nenhum follow-up agendado</span></li>';
    } else {
      d.proximos_followups.forEach(l => {
        const li = document.createElement('li');
        li.innerHTML = `
          <span class="ml-name">${l.nome || '—'}</span>
          <span class="ml-date">${fmtDate(l.proximo_followup_em)}</span>`;
        li.style.cursor = 'pointer';
        li.onclick = () => window.location = `/leads`;
        fuList.appendChild(li);
      });
    }

    // Recentes list
    const recList = document.getElementById('list-recentes');
    recList.innerHTML = '';
    if (d.recentes.length === 0) {
      recList.innerHTML = '<li><span class="ml-empty">Nenhum lead ainda</span></li>';
    } else {
      d.recentes.forEach(l => {
        const li = document.createElement('li');
        li.innerHTML = `
          <span class="ml-name">${l.nome || '—'}</span>
          <span class="ml-date">${fmtDate(l.data_criacao)}</span>`;
        li.style.cursor = 'pointer';
        li.onclick = () => window.location = `/leads`;
        recList.appendChild(li);
      });
    }

    // Timestamp
    document.getElementById('last-update').textContent =
      'Atualizado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

// ===== Análises de Conversa =====

function confEmoji(score) {
  if (score >= 9) return '💚';
  if (score >= 7) return '🟢';
  if (score >= 4) return '🟡';
  return '🔴';
}

function confLabel(score) {
  if (score >= 9) return 'Quase certa';
  if (score >= 7) return 'Promissora';
  if (score >= 4) return 'Incerta';
  return 'Baixa';
}

async function loadAnalises() {
  try {
    const res = await fetch('/api/analises/stats');
    if (!res.ok) return;
    const d = await res.json();

    if (!d.total) return;  // Sem análises ainda — mantém seção oculta

    document.getElementById('analises-section').style.display = '';

    document.getElementById('analise-total').textContent = d.total;
    document.getElementById('analise-avg').textContent =
      d.avg_confianca !== null ? `${d.avg_confianca}/10` : '—';

    // Distribuição
    const dist = d.distribuicao || {};
    const buckets = [
      { key: 'baixa',       label: 'Baixa',       emoji: '🔴', color: '#ef4444' },
      { key: 'incerta',     label: 'Incerta',      emoji: '🟡', color: '#f59e0b' },
      { key: 'promissora',  label: 'Promissora',   emoji: '🟢', color: '#10b981' },
      { key: 'quase_certa', label: 'Quase certa',  emoji: '💚', color: '#059669' },
    ];
    const distEl = document.getElementById('analise-dist');
    distEl.innerHTML = '';
    buckets.forEach(b => {
      const n = dist[b.key] || 0;
      const chip = document.createElement('div');
      chip.className = 'analise-chip';
      chip.style.borderColor = b.color;
      chip.innerHTML = `<span class="analise-chip-emoji">${b.emoji}</span><span class="analise-chip-label">${b.label}</span><span class="analise-chip-count" style="color:${b.color}">${n}</span>`;
      distEl.appendChild(chip);
    });

    // Últimas análises
    const list = document.getElementById('analises-recentes');
    list.innerHTML = '';
    (d.recentes || []).forEach(a => {
      const score = a.confianca_analise;
      const li = document.createElement('li');
      li.className = 'analise-item';
      li.innerHTML = `
        <span class="analise-score">${confEmoji(score)} ${score}/10</span>
        <span class="analise-nome">${a.nome || a.lead_id || '—'}</span>
        <span class="analise-resumo">${(a.resumo || '').slice(0, 80)}${(a.resumo || '').length > 80 ? '…' : ''}</span>
        <span class="analise-data">${fmtDate(a.data_hora)}</span>`;
      list.appendChild(li);
    });
  } catch (e) {
    console.error('loadAnalises error:', e);
  }
}

loadDashboard();
loadAnalises();
// Auto-refresh every 2 minutes
setInterval(() => { loadDashboard(); loadAnalises(); }, 120_000);
