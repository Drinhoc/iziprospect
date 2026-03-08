/* estatisticas.js — Página /estatisticas */

const FUNIL_ORDER = ['novo','em contato','qualificado','proposta enviada','negociando','fechado'];
const FUNIL_COLORS = {
  'novo':             '#9ca3af',
  'em contato':       '#3b82f6',
  'qualificado':      '#8b5cf6',
  'proposta enviada': '#f59e0b',
  'negociando':       '#f97316',
  'fechado':          '#10b981',
  'perdido':          '#ef4444',
  'sem resposta':     '#6b7280',
  'contato inválido': '#d1d5db',
};

function fmtDate(s) {
  if (!s) return '—';
  return s.slice(0, 10).split('-').reverse().join('/');
}

function fmtMoney(v) {
  if (!v || v === 0) return '—';
  return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pctColor(pct) {
  if (pct >= 80) return '#10b981';
  if (pct >= 50) return '#f59e0b';
  return '#ef4444';
}

/* ---------- Funil ---------- */
function renderFunil(funil) {
  const el = document.getElementById('funil-chart');
  el.innerHTML = '';
  const total = funil['novo'] || Object.values(funil).reduce((a, b) => a + b, 0) || 1;

  const allStatus = [...FUNIL_ORDER];
  // add remaining (perdido, sem resposta, etc.) at the end
  Object.keys(funil).forEach(s => { if (!allStatus.includes(s)) allStatus.push(s); });

  allStatus.forEach(status => {
    const val = funil[status] || 0;
    if (!val) return;
    const pct = Math.round(val * 100 / total);
    const color = FUNIL_COLORS[status] || '#9ca3af';
    const row = document.createElement('div');
    row.className = 'funil-row';
    row.innerHTML = `
      <div class="funil-label">
        <span class="funil-status">${status}</span>
        <span class="funil-count">${val}</span>
      </div>
      <div class="funil-track">
        <div class="funil-fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="funil-pct">${pct}%</span>`;
    el.appendChild(row);
  });
}

/* ---------- Rankings ---------- */
function renderRanking(containerId, data, labelKey) {
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  if (!data || !data.length) {
    el.innerHTML = '<span class="no-data">Sem dados</span>';
    return;
  }
  const maxVal = Math.max(...data.map(r => r.total));
  data.forEach((r, i) => {
    const pct = maxVal > 0 ? Math.round(r.total * 100 / maxVal) : 0;
    const taxa = r.taxa !== null && r.taxa !== undefined ? `${r.taxa}%` : '—';
    const item = document.createElement('div');
    item.className = 'rank-item';
    item.innerHTML = `
      <div class="rank-label-row">
        <span class="rank-pos">${i + 1}</span>
        <span class="rank-name">${r[labelKey] || '—'}</span>
        <span class="rank-meta">${r.total} leads · ${r.fechados || 0} fechados · <span class="rank-taxa">${taxa}</span></span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${pct}%;background:#3b82f6"></div>
      </div>`;
    el.appendChild(item);
  });
}

/* ---------- Análises por segmento ---------- */
function renderAnalisesPorSegmento(data) {
  const el = document.getElementById('analises-por-segmento');
  el.innerHTML = '';
  if (!data || !data.length) {
    el.innerHTML = '<span class="no-data">Sem dados</span>';
    return;
  }
  data.forEach(r => {
    const score = parseFloat(r.avg_confianca) || 0;
    const emoji = score >= 9 ? '💚' : score >= 7 ? '🟢' : score >= 4 ? '🟡' : '🔴';
    const row = document.createElement('div');
    row.className = 'seg-analise-row';
    row.innerHTML = `
      <span class="seg-analise-nome">${r.segmento}</span>
      <span class="seg-analise-score">${emoji} ${r.avg_confianca}/10</span>
      <span class="seg-analise-total">${r.total} análises</span>`;
    el.appendChild(row);
  });
}

/* ---------- Distribuição de scores 1-10 ---------- */
function renderDistScores(distScores) {
  const el = document.getElementById('dist-scores-chart');
  el.innerHTML = '';
  const maxVal = Math.max(...Object.values(distScores).map(Number), 1);
  for (let i = 1; i <= 10; i++) {
    const val = distScores[String(i)] || 0;
    const pct = Math.round(val * 100 / maxVal);
    const color = i >= 9 ? '#059669' : i >= 7 ? '#10b981' : i >= 4 ? '#f59e0b' : '#ef4444';
    const col = document.createElement('div');
    col.className = 'score-col';
    col.innerHTML = `
      <div class="score-bar-wrap">
        <span class="score-val">${val > 0 ? val : ''}</span>
        <div class="score-bar" style="height:${Math.max(pct, 2)}%;background:${color}"></div>
      </div>
      <span class="score-label">${i}</span>`;
    el.appendChild(col);
  }
}

/* ---------- Timeline ---------- */
function renderTimeline(timeline) {
  const el = document.getElementById('timeline-chart');
  el.innerHTML = '';
  if (!timeline || !timeline.length) {
    el.innerHTML = '<span class="no-data">Sem atividade nos últimos 30 dias</span>';
    return;
  }
  const maxVal = Math.max(...timeline.map(t => t.total), 1);
  timeline.forEach(t => {
    const pct = Math.round(t.total * 100 / maxVal);
    const label = t.dia ? t.dia.slice(5).replace('-', '/') : '';
    const col = document.createElement('div');
    col.className = 'tl-col';
    col.innerHTML = `
      <span class="tl-val">${t.total > 0 ? t.total : ''}</span>
      <div class="tl-bar" style="height:${Math.max(pct, 2)}%"></div>
      <span class="tl-label">${label}</span>`;
    el.appendChild(col);
  });
}

/* ---------- Fechamentos ---------- */
function renderFechamentos(fechamentos) {
  const el = document.getElementById('fechamentos-list');
  if (!fechamentos || !fechamentos.length) {
    el.innerHTML = '<span class="no-data">Nenhum fechamento registrado ainda.</span>';
    return;
  }
  el.innerHTML = '';
  fechamentos.forEach(f => {
    const row = document.createElement('div');
    row.className = 'fechamento-row';
    row.innerHTML = `
      <span class="fech-nome">${f.nome || '—'}</span>
      <span class="fech-meta">${[f.cidade, f.segmento].filter(Boolean).join(' · ') || '—'}</span>
      <span class="fech-valor">${fmtMoney(f.valor_venda)}</span>
      <span class="fech-data">${fmtDate(f.data_fechamento) || fmtDate(f.ultima_interacao_em)}</span>`;
    el.appendChild(row);
  });
}

/* ---------- Leads Problemáticos ---------- */
function renderProblematicos(data) {
  const badge = document.getElementById('problematicos-badge');
  badge.textContent = data.length;
  badge.style.background = data.length > 0 ? '#ef4444' : '#9ca3af';

  const el = document.getElementById('problematicos-list');
  if (!data || !data.length) {
    el.innerHTML = '<span class="no-data">Nenhum lead parado no momento 🎉</span>';
    return;
  }
  el.innerHTML = '';
  data.forEach(l => {
    const dias = l.ultima_atividade
      ? Math.round((Date.now() - new Date(l.ultima_atividade)) / 86400000)
      : null;
    const diasTxt = dias !== null ? `${dias}d sem atividade` : 'Nunca teve atividade';
    const row = document.createElement('div');
    row.className = 'prob-row';
    row.innerHTML = `
      <span class="prob-nome">${l.nome || l.lead_id}</span>
      <span class="prob-status status-badge status-${(l.status || '').replace(/\s+/g, '-')}">${l.status || '—'}</span>
      <span class="prob-dias">${diasTxt}</span>
      <a href="/leads" class="prob-link">Ver →</a>`;
    el.appendChild(row);
  });
}

/* ---------- Qualidade dos Dados ---------- */
function renderQualidade(q) {
  const el = document.getElementById('qualidade-chart');
  el.innerHTML = '';
  const fields = [
    { label: 'Telefone (WhatsApp)', pct: q.pct_telefone },
    { label: 'E-mail',              pct: q.pct_email },
    { label: 'Cidade',              pct: q.pct_cidade },
    { label: 'Segmento',            pct: q.pct_segmento },
    { label: 'Fonte',               pct: q.pct_fonte },
    { label: 'Responsável',         pct: q.pct_responsavel },
  ];
  fields.forEach(f => {
    const color = pctColor(f.pct);
    const row = document.createElement('div');
    row.className = 'qual-row';
    row.innerHTML = `
      <div class="qual-label-row">
        <span>${f.label}</span>
        <span style="color:${color};font-weight:600">${f.pct}%</span>
      </div>
      <div class="qual-track">
        <div class="qual-fill" style="width:${f.pct}%;background:${color}"></div>
      </div>`;
    el.appendChild(row);
  });
}

/* ---------- Motivos de Perda ---------- */
function renderMotivos(data) {
  if (!data || !data.length) return;
  document.getElementById('motivos-section').style.display = '';
  const el = document.getElementById('motivos-chart');
  el.innerHTML = '';
  const maxVal = Math.max(...data.map(m => m.total), 1);
  data.forEach(m => {
    const pct = Math.round(m.total * 100 / maxVal);
    const row = document.createElement('div');
    row.className = 'bar-item';
    row.innerHTML = `
      <div class="bar-label-row">
        <strong>${m.motivo}</strong>
        <span>${m.total}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${pct}%;background:#ef4444"></div>
      </div>`;
    el.appendChild(row);
  });
}

/* ---------- Load principal ---------- */
async function loadEstatisticas() {
  try {
    const res = await fetch('/api/estatisticas');
    if (!res.ok) throw new Error('API error');
    const d = await res.json();

    // KPIs
    const k = d.kpis || {};
    document.getElementById('kpi-total').textContent = k.total_leads ?? '—';
    document.getElementById('kpi-fechados').textContent = k.total_fechados ?? '—';
    document.getElementById('kpi-taxa').textContent = k.taxa_conversao != null ? `${k.taxa_conversao}%` : '—';
    document.getElementById('kpi-valor').textContent = fmtMoney(k.valor_total_vendas);
    document.getElementById('kpi-vencidos').textContent = k.followups_vencidos ?? '—';
    document.getElementById('kpi-sem-resposta').textContent = k.total_sem_resposta ?? '—';

    // Funil
    renderFunil(d.funil || {});

    // Rankings
    renderRanking('rank-cidade', d.por_cidade, 'cidade');
    renderRanking('rank-segmento', d.por_segmento, 'segmento');
    renderRanking('rank-fonte', d.por_fonte, 'fonte');
    if (d.por_responsavel && d.por_responsavel.length) {
      renderRanking('rank-responsavel', d.por_responsavel, 'responsavel');
    } else {
      document.getElementById('rank-responsavel-card').style.display = 'none';
    }

    // Análises
    const analises = d.analises_por_segmento || [];
    const distScores = d.dist_scores || {};
    const totalAnalises = Object.values(distScores).reduce((a, b) => a + Number(b), 0);
    if (totalAnalises > 0) {
      document.getElementById('analises-est-section').style.display = '';
      document.getElementById('est-analises-total').textContent = totalAnalises;
      const scores = Object.entries(distScores).map(([k, v]) => Number(k) * Number(v));
      const avgScore = scores.reduce((a, b) => a + b, 0) / totalAnalises;
      document.getElementById('est-analises-avg').textContent = avgScore.toFixed(1) + '/10';
      renderAnalisesPorSegmento(analises);
      renderDistScores(distScores);
    }

    // Timeline
    renderTimeline(d.timeline || []);

    // Fechamentos
    renderFechamentos(d.fechamentos || []);

    // Problemáticos
    renderProblematicos(d.problematicos || []);

    // Qualidade
    renderQualidade(d.qualidade || {});

    // Motivos de perda
    renderMotivos(d.motivos_perda || []);

    // Timestamp
    document.getElementById('last-update-stats').textContent =
      'Atualizado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  } catch (e) {
    console.error('loadEstatisticas error:', e);
  }
}

loadEstatisticas();
setInterval(loadEstatisticas, 120_000);
