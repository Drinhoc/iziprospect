/* estatisticas.js — Página /estatisticas */

const FUNIL_ORDER = ['novo','1º contato','sem resposta','qualificado','em espera','negociando','fechado'];
const FUNIL_COLORS = {
  'novo':             '#9ca3af',
  '1º contato':       '#06b6d4',
  'sem resposta':     '#6b7280',
  'qualificado':      '#8b5cf6',
  'em espera':        '#d97706',
  'proposta enviada': '#f59e0b',
  'negociando':       '#f97316',
  'fechado':          '#10b981',
  'perdido':          '#ef4444',
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

/* ---------- Funil de Conversão ---------- */
function renderFunilConversao(data) {
  const el = document.getElementById('funil-conversao');
  if (!el) return;

  const stages = [
    { key: 'total',          label: 'Leads gerados',    color: '#9ca3af', desc: 'cadastrados no CRM' },
    { key: 'contatados',     label: 'Contatados',       color: '#3b82f6', desc: 'primeiro contato feito' },
    { key: 'responderam',    label: 'Responderam',      color: '#8b5cf6', desc: 'houve interação real' },
    { key: 'conversas_reais',label: 'Conversas reais',  color: '#f97316', desc: 'demonstraram interesse' },
    { key: 'fechados',       label: 'Vendas fechadas',  color: '#10b981', desc: 'convertidos' },
  ];

  const total = data.total || 1;
  let html = '';

  stages.forEach((stage, i) => {
    const val = data[stage.key] || 0;
    const pct = total > 0 ? Math.round(val * 100 / total) : 0;

    html += `
      <div class="fc-row">
        <div class="fc-meta">
          <span class="fc-count">${val}</span>
          <div class="fc-labels">
            <span class="fc-label">${stage.label}</span>
            <span class="fc-desc">${stage.desc}</span>
          </div>
        </div>
        <div class="fc-bar-track">
          <div class="fc-bar-fill" style="width:${Math.max(pct, val > 0 ? 1 : 0)}%;background:${stage.color}"></div>
        </div>
        <span class="fc-pct">${pct}%</span>
      </div>`;

    if (i < stages.length - 1) {
      const nextVal = data[stages[i + 1].key] || 0;
      const convPct = val > 0 ? Math.round(nextVal * 100 / val) : 0;
      const convColor = convPct >= 30 ? '#10b981' : convPct >= 10 ? '#f59e0b' : '#ef4444';
      html += `
        <div class="fc-connector">
          <div class="fc-conn-arrow">↓</div>
          <div class="fc-conn-rate" style="color:${convColor}">${convPct}% avançaram</div>
          <div class="fc-conn-lost">${val - nextVal > 0 ? `− ${val - nextVal} saíram` : ''}</div>
        </div>`;
    }
  });

  // Taxa total de conversão em destaque
  const fechados = data.fechados || 0;
  const taxaTotal = total > 1 ? (fechados / data.total * 100).toFixed(1) : '0.0';
  const taxaColor = parseFloat(taxaTotal) >= 10 ? '#10b981' : parseFloat(taxaTotal) >= 3 ? '#f59e0b' : '#ef4444';
  html += `<div class="fc-taxa-total">Taxa total <strong style="color:${taxaColor}">${taxaTotal}%</strong> <span class="fc-taxa-sub">(de lead gerado a venda fechada)</span></div>`;

  el.innerHTML = html;
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

/* ---------- Estatísticas detalhadas por segmento ---------- */
const SEGMENTO_LABEL_MAP = {
  'odontologia': 'Odontologia',
  'medicina':    'Medicina',
  'estetica':    'Estética',
  'psicologia':  'Psicologia',
  'outros':      'Outros',
};

function renderSegmentoDetalhado(data) {
  const el = document.getElementById('seg-detalhe-list');
  el.innerHTML = '';
  if (!data || !data.length) {
    el.innerHTML = '<span class="no-data">Sem dados de segmento ainda.</span>';
    return;
  }
  const STATUS_COLORS = {
    'novo':             '#9ca3af',
    '1º contato':       '#06b6d4',
    'sem resposta':     '#6b7280',
    'qualificado':      '#8b5cf6',
    'em espera':        '#d97706',
    'negociando':       '#f97316',
    'fechado':          '#10b981',
    'perdido':          '#ef4444',
    'contato inválido': '#d1d5db',
    'proposta enviada': '#f59e0b',
  };
  data.forEach(seg => {
    const segLabel = SEGMENTO_LABEL_MAP[seg.segmento] || (seg.segmento.charAt(0).toUpperCase() + seg.segmento.slice(1));
    const card = document.createElement('div');
    card.className = 'seg-detalhe-card';

    // Status bars
    const barsHtml = Object.entries(seg.status || {})
      .sort((a, b) => b[1] - a[1])
      .map(([st, cnt]) => {
        const pct = Math.round(cnt * 100 / (seg.total || 1));
        const color = STATUS_COLORS[st] || '#9ca3af';
        return `<div class="seg-bar-row">
          <span class="seg-bar-label">${st}</span>
          <div class="seg-bar-track">
            <div class="seg-bar-fill" style="width:${pct}%;background:${color}"></div>
          </div>
          <span class="seg-bar-count">${cnt}</span>
        </div>`;
      }).join('');

    const taxaColor = seg.taxa_conversao >= 20 ? '#10b981' : seg.taxa_conversao >= 5 ? '#f59e0b' : '#9ca3af';
    card.innerHTML = `
      <div class="seg-detalhe-header">
        <span class="seg-detalhe-nome">${segLabel}</span>
        <span class="seg-detalhe-total">${seg.total} leads</span>
        <span class="seg-detalhe-taxa" style="color:${taxaColor}">${seg.taxa_conversao}% conv.</span>
      </div>
      <div class="seg-detalhe-bars">${barsHtml}</div>`;
    el.appendChild(card);
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

    // Funil de Conversão
    renderFunilConversao(d.funil_conversao || {});

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

    // Segmento detalhado
    renderSegmentoDetalhado(d.segmento_detalhado || []);

    // Timestamp
    document.getElementById('last-update-stats').textContent =
      'Atualizado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  } catch (e) {
    console.error('loadEstatisticas error:', e);
  }
}

loadEstatisticas();
setInterval(loadEstatisticas, 120_000);

// ═══════════════════════════════════════════════════════════════
// INTELIGÊNCIA IA — carregado via endpoint separado /api/ia/stats
// ═══════════════════════════════════════════════════════════════

function fmtAudioDurEst(s) {
  if (!s) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}min ${sec}s` : `${sec}s`;
}

function confBar(valor, max) {
  const pct = max > 0 ? Math.round((valor / max) * 100) : 0;
  const cor = valor >= 0.7 ? '#10b981' : valor >= 0.4 ? '#f59e0b' : '#ef4444';
  return `<div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${cor}"></div></div>`;
}

async function loadIaStats() {
  try {
    const res = await fetch('/api/ia/stats');
    if (!res.ok) return;
    const d = await res.json();

    if (!d.totais || d.totais.total_processadas === 0) return;

    const t = d.totais;

    // KPIs
    document.getElementById('ia-kpis-section').style.display = '';
    document.getElementById('ia-total-proc').textContent = t.total_processadas.toLocaleString('pt-BR');
    document.getElementById('ia-conf-global').textContent =
      t.confianca_global !== null ? `${Math.round(t.confianca_global * 100)}%` : '—';
    document.getElementById('ia-baixa-conf').textContent = t.baixa_confianca_count;
    document.getElementById('ia-total-audio').textContent = t.total_audios.toLocaleString('pt-BR');
    document.getElementById('ia-dur-audio').textContent = fmtAudioDurEst(t.duracao_audio_media_s);

    // Top ações
    if (d.top_acoes && d.top_acoes.length > 0) {
      document.getElementById('ia-acoes-section').style.display = '';
      const maxAcao = d.top_acoes[0].total;
      document.getElementById('ia-acoes-chart').innerHTML = d.top_acoes.map(a => {
        const pct = maxAcao > 0 ? Math.round((a.total / maxAcao) * 100) : 0;
        return `<div class="bar-item">
          <div class="bar-label-row"><strong>${a.acao}</strong><span>${a.total}</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:#6366f1"></div></div>
        </div>`;
      }).join('');
    }

    // Confiança por tipo
    if (d.confianca_por_tipo && d.confianca_por_tipo.length > 0) {
      document.getElementById('ia-conf-tipo-section').style.display = '';
      const tipoEmoji = { audio: '🎙️', text: '💬', image: '🖼️', texto: '💬' };
      document.getElementById('ia-conf-tipo-list').innerHTML = d.confianca_por_tipo.map(c => {
        const emoji = tipoEmoji[c.tipo] || '📩';
        const pct = Math.round(c.confianca_media * 100);
        const cor = c.confianca_media >= 0.7 ? '#10b981' : c.confianca_media >= 0.4 ? '#f59e0b' : '#ef4444';
        return `<div class="ia-conf-row">
          <span class="ia-conf-tipo">${emoji} ${c.tipo}</span>
          <span class="ia-conf-n">${c.total} msgs</span>
          <div class="ia-conf-bar-wrap">
            <div class="bar-track" style="flex:1"><div class="bar-fill" style="width:${pct}%;background:${cor}"></div></div>
            <span class="ia-conf-pct" style="color:${cor}">${pct}%</span>
          </div>
        </div>`;
      }).join('');
    }

    // Baixa confiança — para revisão
    if (d.baixa_confianca && d.baixa_confianca.length > 0) {
      document.getElementById('ia-revisao-section').style.display = '';
      const fmtData = s => s ? s.slice(0, 16).replace('T', ' ') : '—';
      document.getElementById('ia-revisao-list').innerHTML = `
        <div class="ia-revisao-table">
          ${d.baixa_confianca.map(r => {
            const pct = r.confianca_ia !== null ? Math.round(r.confianca_ia * 100) : 0;
            const tipoEmoji = r.tipo === 'audio' ? '🎙️' : r.tipo === 'image' ? '🖼️' : '💬';
            return `<div class="ia-revisao-row">
              <span class="ia-rev-tipo">${tipoEmoji}</span>
              <span class="ia-rev-nome">${r.nome || r.lead_id || '—'}</span>
              <span class="ia-rev-acao">${r.acao_executada || '—'}</span>
              <span class="ia-rev-conf" style="color:#ef4444">${pct}%</span>
              <span class="ia-rev-data">${fmtData(r.data_hora)}</span>
            </div>`;
          }).join('')}
        </div>`;
    }
  } catch (e) {
    console.error('loadIaStats error:', e);
  }
}

loadIaStats();
setInterval(loadIaStats, 120_000);

/* ═══════════════════════════════════════════════
   TESTE A/B — MENSAGEM INICIAL
   ═══════════════════════════════════════════════ */

const SEG_LABEL = {
  odontologia: 'Odontologia', medicina: 'Medicina',
  estetica: 'Estética', psicologia: 'Psicologia',
  nutricionista: 'Nutricionista', fisioterapia: 'Fisioterapia',
  veterinaria: 'Veterinária', outros: 'Outros',
};

function renderAbStats(d) {
  const section = document.getElementById('ab-section');
  const el = document.getElementById('ab-stats-content');
  if (!d || !d.variantes || Object.keys(d.variantes).length === 0) return;

  section.classList.remove('hidden');
  const variantes = d.variantes;
  const vars = ['A', 'B', 'C'].filter(v => variantes[v]);

  // Cards por variante
  const varCards = vars.map(v => {
    const info = variantes[v] || { copiadas: 0, responderam: 0, taxa: 0 };
    const taxaColor = info.taxa >= 30 ? '#10b981' : info.taxa >= 15 ? '#f59e0b' : '#ef4444';
    return `
      <div class="ab-card">
        <div class="ab-card-header">
          <span class="ab-variant-badge ab-variant-${v}">Variante ${v}</span>
          <span class="ab-taxa" style="color:${taxaColor}">${info.taxa}%</span>
        </div>
        <div class="ab-metrics">
          <div class="ab-metric">
            <span class="ab-metric-val">${info.copiadas}</span>
            <span class="ab-metric-label">Enviadas</span>
          </div>
          <div class="ab-metric">
            <span class="ab-metric-val">${info.responderam}</span>
            <span class="ab-metric-label">Responderam</span>
          </div>
        </div>
        <div class="ab-bar-track">
          <div class="ab-bar-fill" style="width:${Math.min(info.taxa, 100)}%;background:${taxaColor}"></div>
        </div>
      </div>`;
  }).join('');

  // Tabela por segmento
  let segTable = '';
  if (d.por_segmento && d.por_segmento.length) {
    const rows = d.por_segmento.map(s => {
      const aC = s['A_copiadas'] || 0, aR = s['A_responderam'] || 0;
      const bC = s['B_copiadas'] || 0, bR = s['B_responderam'] || 0;
      const cC = s['C_copiadas'] || 0, cR = s['C_responderam'] || 0;
      const aTaxa = aC ? Math.round(aR * 100 / aC) : 0;
      const bTaxa = bC ? Math.round(bR * 100 / bC) : 0;
      const cTaxa = cC ? Math.round(cR * 100 / cC) : 0;
      const best = Math.max(aTaxa, bTaxa, cTaxa);
      const winner = best === 0 ? '' : aTaxa === best ? 'A' : bTaxa === best ? 'B' : 'C';
      return `<tr>
        <td>${SEG_LABEL[s.segmento] || s.segmento}</td>
        <td>${aC} / ${aR} <span class="ab-taxa-sm">(${aTaxa}%)</span>${winner === 'A' ? ' <span class="ab-winner">↑</span>' : ''}</td>
        <td>${bC} / ${bR} <span class="ab-taxa-sm">(${bTaxa}%)</span>${winner === 'B' ? ' <span class="ab-winner">↑</span>' : ''}</td>
        <td>${cC} / ${cR} <span class="ab-taxa-sm">(${cTaxa}%)</span>${winner === 'C' ? ' <span class="ab-winner">↑</span>' : ''}</td>
      </tr>`;
    }).join('');
    segTable = `
      <h3 class="ab-sub-title">Por segmento <span style="font-weight:400;font-size:.75rem">(enviadas / responderam)</span></h3>
      <div class="ab-table-wrap">
        <table class="ab-table">
          <thead><tr><th>Segmento</th><th>Variante A</th><th>Variante B</th><th>Variante C</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  el.innerHTML = `<div class="ab-cards-row">${varCards}</div>${segTable}`;
}

async function loadAbStats() {
  try {
    const res = await fetch('/api/msg-ab/stats');
    if (!res.ok) return;
    renderAbStats(await res.json());
  } catch {}
}

loadAbStats();
setInterval(loadAbStats, 60_000);
