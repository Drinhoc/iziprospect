/* Leads page JS */

let state = {
  page: 1,
  pageSize: 50,
  total: 0,
  search: '',
  status: '',
  segmento: '',
  searchTimer: null,
  currentLeadId: null,
};

// ===== Badges =====

const SEGMENTO_LABEL = {
  'odontologia': 'Odontologia',
  'medicina':    'Medicina',
  'estetica':    'Estética',
  'psicologia':  'Psicologia',
  'outros':      'Outros',
};

function segLabel(s) {
  return SEGMENTO_LABEL[s] || (s ? s.charAt(0).toUpperCase() + s.slice(1) : '—');
}

function statusBadge(s) {
  const map = {
    'novo':             'badge-novo',
    'em contato':       'badge-em-contato',
    'qualificado':      'badge-qualificado',
    'em espera':        'badge-em-espera',
    'proposta enviada': 'badge-proposta',
    'negociando':       'badge-negociando',
    'fechado':          'badge-fechado',
    'perdido':          'badge-perdido',
    'sem resposta':     'badge-sem-resposta',
    'contato inválido': 'badge-perdido',
    'arquivado':        'badge-arquivado',
  };
  const cls = map[s] || 'badge-novo';
  return `<span class="badge ${cls}">${s || '—'}</span>`;
}

function fmtDate(s) {
  if (!s) return '—';
  return s.slice(0, 10).split('-').reverse().join('/');
}

function fmtPhone(s) {
  if (!s) return null;
  return s.replace(/^\+55/, '').replace(/(\d{2})(\d{4,5})(\d{4})/, '($1) $2-$3').trim();
}

// ===== Load leads =====

async function loadLeads() {
  document.getElementById('loading-state').classList.remove('hidden');
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('pagination').classList.add('hidden');

  const params = new URLSearchParams({
    page: state.page,
    page_size: state.pageSize,
  });
  if (state.search) params.set('search', state.search);
  if (state.status) params.set('status', state.status);
  if (state.segmento) params.set('segmento', state.segmento);

  try {
    const res = await fetch('/api/leads?' + params);
    if (!res.ok) throw new Error('API error');
    const data = await res.json();

    state.total = data.total;
    document.getElementById('loading-state').classList.add('hidden');
    document.getElementById('total-label').textContent =
      `${data.total} lead${data.total !== 1 ? 's' : ''}`;

    if (data.leads.length === 0) {
      document.getElementById('empty-state').classList.remove('hidden');
    } else {
      renderTable(data.leads);
      renderCards(data.leads);
    }

    renderPagination(data.total, data.page, data.page_size);
  } catch (e) {
    document.getElementById('loading-state').classList.add('hidden');
    console.error('loadLeads error:', e);
  }
}

function renderTable(leads) {
  const tbody = document.getElementById('leads-tbody');
  tbody.innerHTML = '';
  leads.forEach(l => {
    const phone = fmtPhone(l.whatsapp);
    const phoneTd = phone
      ? `${phone} <button class="copy-phone-btn" data-phone="${esc(l.whatsapp)}" title="Copiar">⎘</button>`
      : '—';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="lead-name">${esc(l.nome)}</span></td>
      <td class="text-muted">${segLabel(l.segmento)}</td>
      <td class="text-muted">${esc(l.cidade) || '—'}</td>
      <td class="td-phone">${phoneTd}</td>
      <td class="text-muted">${esc(l.responsavel) || '—'}</td>
      <td>${statusBadge(l.status)}</td>
      <td class="text-muted td-pendencia">${esc(l.pendencia) || '—'}</td>
      <td class="text-muted">${fmtDate(l.ultima_interacao_em)}</td>
      <td class="text-muted">${fmtDate(l.proximo_followup_em)}</td>`;
    tr.onclick = () => openLeadModal(l.lead_id);
    // Copy phone button — stop propagation so row click doesn't fire
    tr.querySelectorAll('.copy-phone-btn').forEach(btn => {
      btn.onclick = e => {
        e.stopPropagation();
        const num = btn.dataset.phone || '';
        navigator.clipboard.writeText(num).then(() => {
          const orig = btn.textContent;
          btn.textContent = '✓';
          setTimeout(() => { btn.textContent = orig; }, 1200);
        });
      };
    });
    tbody.appendChild(tr);
  });
}

function renderCards(leads) {
  const container = document.getElementById('leads-cards');
  container.innerHTML = '';
  leads.forEach(l => {
    const card = document.createElement('div');
    card.className = 'lead-card';
    const phone = fmtPhone(l.whatsapp);
    const phoneHtml = phone
      ? `📱 ${phone} <button class="copy-phone-btn" data-phone="${esc(l.whatsapp)}" title="Copiar número">⎘</button>`
      : null;
    const meta = [
      l.segmento ? `🏥 ${segLabel(l.segmento)}` : null,
      l.cidade ? `📍 ${esc(l.cidade)}` : null,
      phoneHtml,
      l.responsavel ? `👤 ${esc(l.responsavel)}` : null,
      l.proximo_followup_em ? `📅 ${fmtDate(l.proximo_followup_em)}` : null,
    ].filter(Boolean);

    card.innerHTML = `
      <div class="lc-top">
        <span class="lc-name">${esc(l.nome) || '—'}</span>
        <div class="lc-badges">${statusBadge(l.status)}</div>
      </div>
      ${meta.length ? `<div class="lc-meta">${meta.map(m => `<span class="lc-meta-item">${m}</span>`).join('')}</div>` : ''}
      ${l.pendencia ? `<div class="lc-pendencia">${esc(l.pendencia)}</div>` : ''}`;
    card.onclick = () => openLeadModal(l.lead_id);
    card.querySelectorAll('.copy-phone-btn').forEach(btn => {
      btn.onclick = e => {
        e.stopPropagation();
        const num = btn.dataset.phone || '';
        navigator.clipboard.writeText(num).then(() => {
          const orig = btn.textContent;
          btn.textContent = '✓';
          setTimeout(() => { btn.textContent = orig; }, 1200);
        });
      };
    });
    container.appendChild(card);
  });
}

function renderPagination(total, page, pageSize) {
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return;
  const el = document.getElementById('pagination');
  el.classList.remove('hidden');
  document.getElementById('page-info').textContent = `Página ${page} de ${pages}`;
  document.getElementById('btn-prev').disabled = page <= 1;
  document.getElementById('btn-next').disabled = page >= pages;
}

function changePage(delta) {
  state.page += delta;
  loadLeads();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== Filters =====

function openFilters() {
  document.getElementById('filters-overlay').classList.remove('hidden');
  document.getElementById('filters-sheet').classList.remove('hidden');
  requestAnimationFrame(() => {
    document.getElementById('filters-overlay').classList.add('visible');
    document.getElementById('filters-sheet').classList.add('visible');
  });
}

function closeFilters() {
  const overlay = document.getElementById('filters-overlay');
  const sheet = document.getElementById('filters-sheet');
  overlay.classList.remove('visible');
  sheet.classList.remove('visible');
  setTimeout(() => {
    overlay.classList.add('hidden');
    sheet.classList.add('hidden');
  }, 280);
}

function applyFilters() {
  state.status = document.getElementById('filter-status').value;
  state.segmento = document.getElementById('filter-segmento').value;
  state.page = 1;
  updateFilterChips();
  loadLeads();
}

function clearFilters() {
  state.status = '';
  state.segmento = '';
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-segmento').value = '';
  state.page = 1;
  updateFilterChips();
  loadLeads();
  closeFilters();
}

function updateFilterChips() {
  const chips = document.getElementById('filter-chips');
  const badge = document.getElementById('filter-badge');
  const active = [
    state.status && { label: `Status: ${state.status}`, clear: () => { state.status = ''; document.getElementById('filter-status').value = ''; } },
    state.segmento && { label: `Segmento: ${segLabel(state.segmento)}`, clear: () => { state.segmento = ''; document.getElementById('filter-segmento').value = ''; } },
  ].filter(Boolean);

  if (active.length === 0) {
    chips.classList.add('hidden');
    badge.classList.add('hidden');
    return;
  }

  chips.classList.remove('hidden');
  badge.classList.remove('hidden');
  badge.textContent = active.length;

  chips.innerHTML = '';
  active.forEach(f => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.textContent = f.label + ' ✕';
    chip.onclick = () => { f.clear(); state.page = 1; updateFilterChips(); loadLeads(); };
    chips.appendChild(chip);
  });
}

// ===== Modal / CRUD =====

async function openLeadModal(leadId) {
  state.currentLeadId = leadId;
  const isNew = !leadId;

  document.getElementById('sheet-title').textContent = isNew ? 'Novo Lead' : 'Editar Lead';
  document.getElementById('form-lead-id').value = leadId || '';
  document.getElementById('btn-archive').classList.toggle('hidden', isNew);
  document.getElementById('readonly-section').classList.toggle('hidden', isNew);

  if (!isNew) {
    try {
      const res = await fetch(`/api/leads/${leadId}`);
      if (!res.ok) throw new Error('not found');
      const l = await res.json();
      fillForm(l);
    } catch (e) {
      console.error('fetch lead error:', e);
      return;
    }
  } else {
    clearForm();
  }

  const overlay = document.getElementById('modal-overlay');
  const sheet = document.getElementById('modal-sheet');
  overlay.classList.remove('hidden');
  sheet.classList.remove('hidden');
  requestAnimationFrame(() => {
    overlay.classList.add('visible');
    sheet.classList.add('visible');
  });

  setTimeout(() => {
    const body = sheet.querySelector('.sheet-body');
    if (body) body.scrollTop = 0;
  }, 50);
}

function closeModal() {
  const overlay = document.getElementById('modal-overlay');
  const sheet = document.getElementById('modal-sheet');
  overlay.classList.remove('visible');
  sheet.classList.remove('visible');
  setTimeout(() => {
    overlay.classList.add('hidden');
    sheet.classList.add('hidden');
  }, 280);
}

function fillForm(l) {
  document.getElementById('f-nome').value = l.nome || '';
  document.getElementById('f-cidade').value = l.cidade || '';
  document.getElementById('f-segmento').value = l.segmento || '';
  document.getElementById('f-status').value = l.status || 'novo';
  document.getElementById('f-whatsapp').value = l.whatsapp || '';
  document.getElementById('f-email').value = l.email || '';
  document.getElementById('f-instagram').value = l.instagram || '';
  document.getElementById('f-site').value = l.site || '';
  document.getElementById('f-responsavel').value = l.responsavel || '';
  document.getElementById('f-fonte').value = l.fonte || '';
  document.getElementById('f-followup').value = (l.proximo_followup_em || '').slice(0, 10);
  document.getElementById('f-pendencia').value = l.pendencia || '';
  document.getElementById('f-observacoes').value = l.observacoes || '';
  document.getElementById('f-valor-venda').value = l.valor_venda || '';
  document.getElementById('f-data-fechamento').value = (l.data_fechamento || '').slice(0, 10);
  document.getElementById('f-motivo-perda').value = l.motivo_perda || '';
  document.getElementById('f-data-criacao').value = (l.data_criacao || '').slice(0, 10);
  updateConditionalFields(l.status || 'novo');

  // Readonly
  document.getElementById('ro-lead-id').textContent = l.lead_id || '';
  document.getElementById('ro-resumo').textContent = l.resumo || '—';
  document.getElementById('ro-ultima').textContent = fmtDate(l.ultima_interacao_em);
}

function updateConditionalFields(status) {
  const isFechado = status === 'fechado';
  const isPerdido = status === 'perdido';
  document.getElementById('fg-fechamento').classList.toggle('hidden', !isFechado);
  document.getElementById('fg-data-fechamento').classList.toggle('hidden', !isFechado);
  document.getElementById('fg-motivo-perda').classList.toggle('hidden', !isPerdido);
}

function clearForm() {
  ['f-nome','f-cidade','f-whatsapp','f-email','f-instagram','f-site','f-responsavel',
   'f-pendencia','f-observacoes','f-valor-venda','f-data-fechamento','f-motivo-perda','f-data-criacao'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('f-segmento').value = '';
  document.getElementById('f-status').value = 'novo';
  document.getElementById('f-fonte').value = '';
  document.getElementById('f-followup').value = '';
  updateConditionalFields('novo');
}

function formData() {
  return {
    nome: document.getElementById('f-nome').value.trim(),
    cidade: document.getElementById('f-cidade').value.trim(),
    segmento: document.getElementById('f-segmento').value,
    status: document.getElementById('f-status').value,
    whatsapp: document.getElementById('f-whatsapp').value.trim(),
    email: document.getElementById('f-email').value.trim(),
    instagram: document.getElementById('f-instagram').value.trim(),
    site: document.getElementById('f-site').value.trim(),
    responsavel: document.getElementById('f-responsavel').value.trim(),
    fonte: document.getElementById('f-fonte').value,
    proximo_followup_em: document.getElementById('f-followup').value || '',
    pendencia: document.getElementById('f-pendencia').value.trim(),
    observacoes: document.getElementById('f-observacoes').value.trim(),
    valor_venda: document.getElementById('f-valor-venda').value || '',
    data_fechamento: document.getElementById('f-data-fechamento').value || '',
    motivo_perda: document.getElementById('f-motivo-perda').value.trim(),
    data_criacao: document.getElementById('f-data-criacao').value || '',
  };
}

async function saveLead(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-save');
  btn.textContent = 'Salvando…';
  btn.disabled = true;

  const data = formData();
  const leadId = document.getElementById('form-lead-id').value;
  const isNew = !leadId;

  try {
    let res;
    if (isNew) {
      res = await fetch('/api/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } else {
      res = await fetch(`/api/leads/${leadId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao salvar');
    }

    closeModal();
    loadLeads();
  } catch (err) {
    alert('Erro: ' + err.message);
  } finally {
    btn.textContent = 'Salvar';
    btn.disabled = false;
  }
}

async function deleteLead() {
  const leadId = document.getElementById('form-lead-id').value;
  if (!leadId) return;
  const nome = document.getElementById('f-nome').value || leadId;
  if (!confirm(`Deletar "${nome}" permanentemente? Esta ação não pode ser desfeita.`)) return;

  try {
    const res = await fetch(`/api/leads/${leadId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Erro ao deletar');
    closeModal();
    loadLeads();
  } catch (err) {
    alert('Erro: ' + err.message);
  }
}

// ===== Helpers =====

function esc(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ===== Init =====

document.getElementById('f-status').addEventListener('change', e => {
  updateConditionalFields(e.target.value);
});

document.getElementById('search-input').addEventListener('input', e => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => {
    state.search = e.target.value.trim();
    state.page = 1;
    loadLeads();
  }, 350);
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeModal();
    closeFilters();
    closeImportModal();
  }
});

// ===== Import =====

const IMPORT_COLUMNS = [
  'nome','cidade','segmento','whatsapp','email',
  'instagram','site','responsavel','fonte',
  'status','observacoes','proximo_followup_em',
];

function openImportModal() {
  document.getElementById('import-textarea').value = '';
  document.getElementById('import-preview').classList.add('hidden');
  document.getElementById('import-result').classList.add('hidden');
  document.getElementById('btn-import-run').textContent = 'Importar';
  document.getElementById('btn-import-run').disabled = false;

  const overlay = document.getElementById('import-overlay');
  const sheet = document.getElementById('import-sheet');
  overlay.classList.remove('hidden');
  sheet.classList.remove('hidden');
  requestAnimationFrame(() => {
    overlay.classList.add('visible');
    sheet.classList.add('visible');
  });
}

function closeImportModal() {
  const overlay = document.getElementById('import-overlay');
  const sheet = document.getElementById('import-sheet');
  overlay.classList.remove('visible');
  sheet.classList.remove('visible');
  setTimeout(() => {
    overlay.classList.add('hidden');
    sheet.classList.add('hidden');
  }, 280);
}

function detectSep(firstLine) {
  if (firstLine.includes('\t')) return '\t';
  if (firstLine.includes(';')) return ';';
  return ',';
}

function parseLine(line, sep) {
  if (sep !== ',') return line.split(sep).map(c => c.trim());
  const cells = [];
  let cur = '', inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { inQ = !inQ; continue; }
    if (ch === ',' && !inQ) { cells.push(cur.trim()); cur = ''; continue; }
    cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

function parseImportText(raw) {
  const lines = raw.split('\n').map(l => l.trimEnd()).filter(l => l.trim());
  if (lines.length < 2) throw new Error('Precisa de pelo menos 1 linha de cabeçalho + 1 linha de dados.');

  const sep = detectSep(lines[0]);
  const headers = parseLine(lines[0], sep).map(h => h.toLowerCase().trim().replace(/\s+/g, '_'));

  if (!headers.includes('nome')) throw new Error("A planilha deve ter uma coluna chamada 'nome'.");

  const validIdx = headers.map((h, i) => IMPORT_COLUMNS.includes(h) ? i : -1);

  return lines.slice(1).map(line => {
    const cells = parseLine(line, sep);
    const obj = {};
    headers.forEach((h, i) => {
      if (validIdx[i] === -1) return;
      const val = (cells[i] || '').trim();
      if (val) obj[h] = val;
    });
    return obj;
  }).filter(o => o.nome);
}

async function runImport() {
  const raw = document.getElementById('import-textarea').value.trim();
  if (!raw) { alert('Cole os dados antes de importar.'); return; }

  let leads;
  try {
    leads = parseImportText(raw);
  } catch (err) {
    alert('Erro ao ler dados: ' + err.message);
    return;
  }

  if (leads.length === 0) {
    alert('Nenhum lead válido encontrado. Verifique se há uma coluna "nome".');
    return;
  }

  const btn = document.getElementById('btn-import-run');
  btn.textContent = `Importando ${leads.length} leads…`;
  btn.disabled = true;

  try {
    const res = await fetch('/api/leads/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ leads }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Erro na API');

    const resultEl = document.getElementById('import-result');
    resultEl.classList.remove('hidden');

    let html = `<div class="import-summary">`;
    html += `<span class="import-ok">✓ ${data.imported} importados</span>`;
    if (data.needs_review > 0)
      html += ` &nbsp; <span class="import-warn">⚠ ${data.needs_review} para revisar</span>`;
    if (data.errors > 0)
      html += ` &nbsp; <span class="import-err">✗ ${data.errors} com erro</span>`;
    html += `</div>`;

    if (data.review && data.review.length > 0) {
      html += `<p class="import-warn-msg">Leads com nome semelhante já existem (precisam de revisão manual):</p><ul>`;
      data.review.forEach(r => {
        html += `<li><strong>${esc(r.nome)}</strong> — possíveis duplicatas: ${r.candidates.map(esc).join(', ')}</li>`;
      });
      html += `</ul>`;
    }

    if (data.failed && data.failed.length > 0) {
      html += `<p class="import-err-msg">Falhas:</p><ul>`;
      data.failed.forEach(f => {
        html += `<li>${esc(f.nome || `linha ${f.index + 2}`)}: ${esc(f.reason)}</li>`;
      });
      html += `</ul>`;
    }

    resultEl.innerHTML = html;
    loadLeads();
  } catch (err) {
    alert('Erro: ' + err.message);
  } finally {
    btn.textContent = 'Importar';
    btn.disabled = false;
  }
}

loadLeads();
