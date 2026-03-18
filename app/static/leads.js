/* Leads page JS */

// ===== Mensagem inicial sugerida =====
// Templates A/B/C por segmento. Variante determinada pelo lead_id (consistente por lead).
// A/B/C — Estratégias distintas:
// A = Apresentação pessoal casual (sem "Vi o perfil", tom de papo)
// B = Dor-primeiro (abre com pergunta sobre o problema deles, sem intro)
// C = Prova social leve (menciona clínicas da região, sem citar o lead)
const MSG_TEMPLATES = {
  odontologia: [
    `Oi! Vi a {{nome}} pesquisando clínicas odontológicas na região 🙂

Queria perguntar rápido: vocês costumam perder agendamentos porque alguma mensagem chegou fora do horário e não foi respondida a tempo?

Tenho ajudado clínicas por aqui a resolver isso pelo WhatsApp, sem precisar contratar alguém extra pra ficar de plantão.

Faz sentido eu te mostrar como em 2 minutos?`,
    `Oi, {{nome}}! Pergunta rápida:

Já perderam paciente porque a recepção estava ocupada ou fora do horário e a mensagem no WhatsApp ficou sem resposta?

Pergunto porque resolvo exatamente isso pra clínicas odontológicas daqui. Posso te explicar em 2 minutinhos?`,
    `Oi, {{nome}}! Sou o Pedro.

Tenho ajudado clínicas odontológicas da região a parar de perder agendamentos por demora no WhatsApp — automatizando respostas e confirmações fora do horário, sem app novo nem contratação.

Vale uma conversa rápida de 2 minutos?`,
  ],
  medicina: [
    `Oi! Vi a {{nome}} pesquisando clínicas médicas na região 🙂

Queria perguntar rápido: vocês costumam perder consultas porque alguma mensagem chegou fora do horário ou a recepção não deu conta de responder a tempo?

Tenho ajudado clínicas por aqui com isso — um assistente no WhatsApp que responde e confirma consulta mesmo quando a recepção está ocupada.

Faz sentido eu te mostrar como em 2 minutos?`,
    `Oi, {{nome}}! Pergunta rápida:

Já perderam consulta porque a recepção não conseguiu responder uma mensagem a tempo — fora do horário ou no pico do dia?

Pergunto porque resolvo exatamente isso pra clínicas médicas daqui. Posso te explicar em 2 minutinhos?`,
    `Oi, {{nome}}! Sou o Pedro.

Tenho ajudado clínicas médicas da região a não perder mais consulta por falta de resposta no WhatsApp — automatizando o atendimento fora do horário sem sobrecarregar a recepção.

Vale uma conversa rápida de 2 minutos?`,
  ],
  estetica: [
    `Oi! Vi a {{nome}} pesquisando clínicas de estética na região 🙂

Queria perguntar rápido: vocês costumam perder clientes porque a mensagem no WhatsApp demorou a ser respondida ou chegou fora do horário?

Tenho ajudado clínicas de estética por aqui com isso — respostas automáticas e agendamento pelo WhatsApp mesmo quando a equipe está em atendimento.

Faz sentido eu te mostrar como em 2 minutos?`,
    `Oi, {{nome}}! Pergunta rápida:

Já perderam cliente porque a mensagem ficou sem resposta enquanto a equipe estava em atendimento ou fora do horário?

Pergunto porque resolvo exatamente isso pra clínicas de estética daqui. Posso te explicar em 2 minutinhos?`,
    `Oi, {{nome}}! Sou o Pedro.

Tenho ajudado clínicas de estética da região a não perder mais cliente por demora no WhatsApp — respostas automáticas e agendamento mesmo fora do horário, sem precisar de alguém disponível o tempo todo.

Vale uma conversa rápida de 2 minutos?`,
  ],
  default: [
    `Oi! Vi a {{nome}} pesquisando clínicas na região 🙂

Queria perguntar rápido: vocês costumam perder atendimentos porque alguma mensagem no WhatsApp chegou fora do horário ou demorou a ser respondida?

Tenho ajudado clínicas por aqui a resolver isso — respostas automáticas e agendamento mesmo quando a equipe está ocupada ou fora do horário.

Faz sentido eu te mostrar como em 2 minutos?`,
    `Oi, {{nome}}! Pergunta rápida:

Já perderam paciente ou cliente porque a mensagem no WhatsApp ficou sem resposta enquanto a equipe estava ocupada ou fora do horário?

Pergunto porque resolvo exatamente isso pra clínicas e consultórios daqui. Posso te explicar em 2 minutinhos?`,
    `Oi, {{nome}}! Sou o Pedro.

Tenho ajudado clínicas e consultórios da região a não perder mais atendimento por demora no WhatsApp — automatizando respostas e agendamentos fora do horário sem complicação.

Vale uma conversa rápida de 2 minutos?`,
  ],
};

// ===== Follow-up 1 (~5 dias sem resposta) =====
const FU1_TEMPLATES = {
  odontologia: [
    `Oi! Tudo bem? 🙂 Passei aqui só pra confirmar se conseguiu ver minha mensagem sobre a assistente virtual para atendimento no WhatsApp. Se não for algo interessante pra vocês no momento, sem problema!`,
    `Oi! Pergunta rápida — vocês costumam perder agendamentos porque a mensagem chegou fora do horário e não foi respondida a tempo? Se sim, posso te mostrar em 2 minutos como resolvo isso pra clínicas odontológicas daqui. 🙂`,
    `Oi! Só passando rapidamente. Estou ajudando algumas clínicas odontológicas da região a automatizar o WhatsApp — queria checar se faria sentido pra vocês. Posso te enviar um vídeo rápido de como funciona?`,
  ],
  medicina: [
    `Oi! Tudo bem? 🙂 Só passando pra confirmar se conseguiu ver minha mensagem sobre automação de atendimento no WhatsApp pra clínicas. Se não for o momento, tudo bem também!`,
    `Oi! Pergunta rápida — vocês costumam perder consultas por mensagens que chegaram fora do horário e não foram respondidas a tempo? Se sim, posso te mostrar como algumas clínicas médicas daqui resolveram isso. 🙂`,
    `Oi! Só passando rapidamente. Estou ajudando algumas clínicas da região a automatizar o atendimento no WhatsApp — quis checar se faria sentido pra vocês também. Posso te enviar um vídeo rápido?`,
  ],
  estetica: [
    `Oi! Tudo bem? 🙂 Passando só pra confirmar se conseguiu ver minha mensagem sobre automação de atendimento no WhatsApp pra clínicas de estética. Se não for algo relevante agora, tudo bem!`,
    `Oi! Pergunta rápida — vocês costumam perder clientes porque a mensagem chegou fora do horário ou demorou pra ser respondida? Posso te mostrar em 2 minutos como estou ajudando clínicas de estética daqui a resolver isso. 🙂`,
    `Oi! Só passando rapidamente. Estou ajudando algumas clínicas de estética da região com automação de WhatsApp — quis checar se faria sentido conhecer. Posso te enviar um vídeo rápido?`,
  ],
  default: [
    `Oi! Tudo bem? 🙂 Só passando pra confirmar se conseguiu ver minha mensagem sobre automação de atendimento no WhatsApp. Se não for o momento, sem problema!`,
    `Oi! Pergunta rápida — vocês costumam perder clientes porque a mensagem chegou fora do horário e demorou a ser respondida? Posso te mostrar em 2 minutos como resolvo isso. 🙂`,
    `Oi! Só passando rapidamente. Estou ajudando alguns negócios da região a automatizar o atendimento no WhatsApp — quis checar se faria sentido pra vocês. Posso te enviar um vídeo rápido?`,
  ],
};

// ===== Follow-up 2 (~10 dias — mais curto, baixa pressão) =====
const FU2_TEMPLATES = {
  odontologia: [
    `Oi! Só passando rapidamente pra saber se faz sentido pra vocês conhecer a solução de automação de atendimento no WhatsApp 🙂 Se preferir, posso enviar um vídeo curto mostrando como funciona.`,
    `Oi! Última mensagem por aqui 🙂 Se o atendimento automatizado no WhatsApp não for prioridade agora, tudo bem — mas se quiser ver como funciona pra clínicas odontológicas, é só falar.`,
    `Oi! Se surgir interesse em automatizar o atendimento da clínica no WhatsApp no futuro, é só me chamar 🙂 Boa sorte com a agenda!`,
  ],
  medicina: [
    `Oi! Só passando rapidamente pra saber se faz sentido conhecer a solução de automação de atendimento no WhatsApp pra clínicas 🙂 Posso enviar um vídeo curto se preferir.`,
    `Oi! Última mensagem por aqui 🙂 Se automação de WhatsApp não for prioridade agora, tudo bem — mas se quiser ver como funciona, é só falar.`,
    `Oi! Se surgir interesse em automatizar o atendimento da clínica no WhatsApp no futuro, é só me chamar 🙂 Boa sorte com a agenda!`,
  ],
  estetica: [
    `Oi! Só passando rapidamente pra saber se faz sentido pra vocês conhecer a automação de atendimento no WhatsApp 🙂 Se preferir, posso enviar um vídeo curto de como funciona.`,
    `Oi! Última mensagem por aqui 🙂 Se automação de WhatsApp não for prioridade agora, tudo bem — mas se quiser ver como funciona pra clínicas de estética, é só falar.`,
    `Oi! Se surgir interesse em automatizar o atendimento no futuro, é só me chamar 🙂 Sucesso com a agenda!`,
  ],
  default: [
    `Oi! Só passando rapidamente pra saber se faz sentido pra vocês conhecer a solução de automação de atendimento no WhatsApp 🙂 Posso enviar um vídeo curto se preferir.`,
    `Oi! Última mensagem por aqui 🙂 Se automação de WhatsApp não for prioridade agora, tudo bem — mas se quiser ver como funciona, é só falar.`,
    `Oi! Se surgir interesse em automatizar o atendimento no WhatsApp no futuro, é só me chamar 🙂 Boa sorte!`,
  ],
};

function _abVariant(leadId) {
  if (!leadId) return 0;
  return leadId.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 3;
}

function _daysSince(dateStr) {
  if (!dateStr) return 0;
  const d = new Date(dateStr.slice(0, 10));
  if (isNaN(d)) return 0;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

function _getMsgTipo(l) {
  if (l.status !== 'contato feito') return 'inicial';
  const ref = l.ultima_interacao_em || l.data_criacao || '';
  const dias = _daysSince(ref);
  if (dias >= 10) return 'fu2';
  if (dias >= 5)  return 'fu1';
  return 'inicial';
}

function _buildMsg(l, tipo) {
  const seg = l.segmento || '';
  let tpls;
  if (tipo === 'fu1') tpls = FU1_TEMPLATES[seg] || FU1_TEMPLATES.default;
  else if (tipo === 'fu2') tpls = FU2_TEMPLATES[seg] || FU2_TEMPLATES.default;
  else tpls = MSG_TEMPLATES[seg] || MSG_TEMPLATES.default;
  const variant = _abVariant(l.lead_id || '');
  return (tpls[variant] || tpls[0]).replace(/{{nome}}/g, (l.nome || 'vocês').trim());
}

function buildMsgInicial(l) {
  return _buildMsg(l, 'inicial');
}

const _MSG_TIPO_LABEL = {
  inicial: 'Mensagem inicial sugerida',
  fu1:     'Follow-up 1 (5+ dias sem resposta)',
  fu2:     'Follow-up 2 (10+ dias sem resposta)',
};

function updateMsgSugerida(l) {
  const sec = document.getElementById('msg-sugerida-section');
  if (!sec) return;
  const show = ['novo', 'contato feito'].includes(l.status);
  sec.classList.toggle('hidden', !show);
  if (!show) return;

  const tipo = _getMsgTipo(l);
  const pre = document.getElementById('msg-sugerida-text');
  const variantLabel = document.getElementById('msg-sugerida-variant');
  const titleEl = sec.querySelector('.msg-sugerida-title');
  const variant = _abVariant(l.lead_id || '');

  pre.textContent = _buildMsg(l, tipo);
  if (variantLabel) variantLabel.textContent = `Variante ${'ABC'[variant]}`;
  if (titleEl) titleEl.textContent = _MSG_TIPO_LABEL[tipo] || _MSG_TIPO_LABEL.inicial;
  sec.dataset.msgTipo = tipo;
}

let state = {
  page: 1,
  pageSize: 50,
  total: 0,
  search: '',
  status: '',
  segmento: '',
  temperatura: '',
  searchTimer: null,
  currentLeadId: null,
  // A/B tracking: status do lead quando o modal foi aberto
  _modalStatusInicial: null,
  _modalSegmento: null,
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
    'contato feito':    'badge-contato-feito',
    'conversando':      'badge-conversando',
    'negociando':       'badge-negociando',
    'fechado':          'badge-fechado',
    'perdido':          'badge-perdido',
    'contato inválido': 'badge-invalido',
  };
  const cls = map[s] || 'badge-novo';
  return `<span class="badge ${cls}">${s || '—'}</span>`;
}

function temperaturaBadge(l) {
  if (['contato inválido'].includes(l.status)) return '';
  const temp = l.temperatura || 'frio';
  const map = {
    'frio':     { cls: 'badge-temp-frio',     dot: '🔵', label: 'Frio' },
    'morno':    { cls: 'badge-temp-morno',    dot: '🟡', label: 'Morno' },
    'engajado': { cls: 'badge-temp-engajado', dot: '🟠', label: 'Engajado' },
    'quente':   { cls: 'badge-temp-quente',   dot: '🔴', label: 'Quente' },
    'cliente':  { cls: 'badge-temp-cliente',  dot: '🟢', label: 'Cliente' },
  };
  const t = map[temp] || map['frio'];
  return `<span class="badge-temp ${t.cls}" title="Temperatura: ${t.label}">${t.dot} ${t.label}</span>`;
}

function fmtDate(s) {
  if (!s) return '—';
  return s.slice(0, 10).split('-').reverse().join('/');
}

function followupCell(s) {
  if (!s) return '<span class="text-muted">—</span>';
  const date = s.slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  let cls = 'text-muted';
  if (date < today) cls = 'followup-vencido';
  else if (date === today) cls = 'followup-hoje';
  return `<span class="${cls}">${date.split('-').reverse().join('/')}</span>`;
}

// Renderiza célula "Próximo passo" unificando data + acao_followup
function _proximoPasso(l) {
  const dateHtml = followupCell(l.proximo_followup_em);
  const acao = l.acao_followup ? `<span class="proxpasso-acao">${esc(l.acao_followup)}</span>` : '';
  if (!l.proximo_followup_em && !l.acao_followup) return '<span class="text-muted">—</span>';
  return `<span class="proxpasso">${dateHtml}${acao}</span>`;
}

function fmtPhone(s) {
  if (!s) return null;
  let n = s.replace(/^\+55/, '');
  // Strip spurious leading zero (old PSTN long-distance prefix: 0 + DDD + number)
  if (/^0\d{10,11}$/.test(n)) n = n.slice(1);
  return n.replace(/(\d{2})(\d{4,5})(\d{4})/, '($1) $2-$3').trim();
}

// ===== Barra de temperatura =====
// Baseada no campo `temperatura` do DB — sem cálculo client-side.

const TEMP_LEVELS = [
  { key: 'frio',     dot: '🔵', label: 'Frio',     cor: '#94a3b8' },
  { key: 'morno',    dot: '🟡', label: 'Morno',    cor: '#eab308' },
  { key: 'engajado', dot: '🟠', label: 'Engajado', cor: '#f97316' },
  { key: 'quente',   dot: '🔴', label: 'Quente',   cor: '#ef4444' },
  { key: 'cliente',  dot: '🟢', label: 'Cliente',  cor: '#10b981' },
];

function updateEngajBar(leads) {
  const bar = document.getElementById('engaj-bar');
  if (!bar) return;
  const counts = { frio: 0, morno: 0, engajado: 0, quente: 0, cliente: 0 };
  leads.forEach(l => {
    const t = l.temperatura || 'frio';
    if (counts[t] !== undefined) counts[t]++;
  });
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!total) { bar.classList.add('hidden'); return; }

  bar.innerHTML = TEMP_LEVELS.map(t => {
    const n = counts[t.key];
    if (!n) return '';
    const pct = Math.round((n / total) * 100);
    return `<span class="engaj-stat" style="--cor:${t.cor}" title="${t.label}: ${n} lead${n !== 1 ? 's' : ''} (${pct}%)">
      <span class="engaj-stat-dot"></span>
      <span class="engaj-stat-label">${t.dot} ${t.label}</span>
      <span class="engaj-stat-count">${n}</span>
    </span>`;
  }).filter(Boolean).join('<span class="engaj-sep"></span>');
  bar.classList.remove('hidden');
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
  if (state.temperatura) params.set('temperatura', state.temperatura);

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
      document.getElementById('engaj-bar')?.classList.add('hidden');
    } else {
      renderTable(data.leads);
      renderCards(data.leads);
      updateEngajBar(data.leads);
    }

    renderPagination(data.total, data.page, data.page_size);
  } catch (e) {
    document.getElementById('loading-state').classList.add('hidden');
    console.error('loadLeads error:', e);
  }
}

function _copyMsgBtn(l) {
  if (!['novo', 'contato feito'].includes(l.status)) return '';
  const tipo = _getMsgTipo(l);
  return `<button class="copy-msg-btn" data-nome="${esc(l.nome)}" data-seg="${l.segmento || ''}" data-lid="${l.lead_id || ''}" data-tipo="${tipo}" data-ulti="${esc(l.ultima_interacao_em || '')}" data-cria="${esc(l.data_criacao || '')}" title="Copiar mensagem">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
  </button>`;
}

function _trackAbEvento(leadId, segmento, evento, tipo = 'inicial') {
  const variante = ['A', 'B', 'C'][_abVariant(leadId)];
  fetch('/api/msg-ab/evento', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_id: leadId, variante, segmento, evento, tipo }),
  }).catch(() => {});
}

function _bindCopyMsgBtns(el) {
  el.querySelectorAll('.copy-msg-btn').forEach(btn => {
    btn.onclick = e => {
      e.stopPropagation();
      const tipo = btn.dataset.tipo || 'inicial';
      const msg = _buildMsg(
        { nome: btn.dataset.nome, segmento: btn.dataset.seg, lead_id: btn.dataset.lid,
          ultima_interacao_em: btn.dataset.ulti, data_criacao: btn.dataset.cria },
        tipo
      );
      navigator.clipboard.writeText(msg).then(() => {
        btn.classList.add('copied');
        setTimeout(() => btn.classList.remove('copied'), 1400);
        _trackAbEvento(btn.dataset.lid, btn.dataset.seg, 'copiada', tipo);
      });
    };
  });
}

function _novoBadgeBtn(l) {
  return `<button class="badge badge-novo badge-novo--btn" data-lid="${l.lead_id}" data-seg="${l.segmento || ''}" title="Marcar como Contato feito">Novo</button>`;
}

function _bindNovoBadgeBtns(el) {
  el.querySelectorAll('.badge-novo--btn').forEach(btn => {
    btn.onclick = async e => {
      e.stopPropagation();
      if (btn.dataset.loading) return;
      btn.dataset.loading = '1';
      await fetch(`/api/leads/${btn.dataset.lid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'contato feito', temperatura: 'frio', origem_primeiro_contato: 'manual' }),
      }).catch(() => {});
      const badge = document.createElement('span');
      badge.className = 'badge badge-contato-feito';
      badge.textContent = 'Contato feito';
      btn.replaceWith(badge);
    };
  });
}

function _waErroBadge(l) {
  if (l.origem_primeiro_contato !== 'auto_erro') return '';
  return `<span class="wa-erro-badge" title="Erro no envio automático — número pode ser inválido ou não está no WhatsApp">⚠️ Nº inválido</span>`;
}

function renderTable(leads) {
  const tbody = document.getElementById('leads-tbody');
  tbody.innerHTML = '';
  leads.forEach(l => {
    const phone = fmtPhone(l.whatsapp);
    const phoneContent = phone
      ? `${phone} <button class="copy-phone-btn" data-phone="${esc(fmtPhone(l.whatsapp) || '')}" title="Copiar">⎘</button>${_copyMsgBtn(l)}`
      : _copyMsgBtn(l) || '—';
    const phoneTd = `${phoneContent}${_waErroBadge(l)}`;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="lead-name">${esc(l.nome)}</span></td>
      <td class="text-muted">${segLabel(l.segmento)}</td>
      <td class="text-muted">${esc(l.cidade) || '—'}</td>
      <td class="td-phone">${phoneTd}</td>
      <td class="text-muted">${esc(l.responsavel) || '—'}</td>
      <td>${l.status === 'novo' ? _novoBadgeBtn(l) : statusBadge(l.status)} ${temperaturaBadge(l)}</td>
      <td class="text-muted">${fmtDate(l.ultima_interacao_em)}</td>
      <td>${_proximoPasso(l)}</td>`;
    tr.onclick = () => openLeadModal(l.lead_id);
    _bindCopyMsgBtns(tr);
    _bindNovoBadgeBtns(tr);
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
      ? `📱 ${phone} <button class="copy-phone-btn" data-phone="${esc(fmtPhone(l.whatsapp) || '')}" title="Copiar número">⎘</button>${_waErroBadge(l)}`
      : _waErroBadge(l) || null;
    const msgTipo = ['novo', 'contato feito'].includes(l.status) ? _getMsgTipo(l) : null;
    const msgBtnLabel = msgTipo === 'fu2' ? 'Follow-up 2' : msgTipo === 'fu1' ? 'Follow-up 1' : 'Mensagem inicial';
    const msgBtnHtml = msgTipo
      ? `<button class="copy-msg-btn copy-msg-btn--card" data-nome="${esc(l.nome)}" data-seg="${l.segmento || ''}" data-lid="${l.lead_id || ''}" data-tipo="${msgTipo}" data-ulti="${esc(l.ultima_interacao_em || '')}" data-cria="${esc(l.data_criacao || '')}" title="Copiar mensagem">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          ${msgBtnLabel}
        </button>`
      : null;
    const proxPassoMeta = l.proximo_followup_em
      ? `📅 ${fmtDate(l.proximo_followup_em)}${l.acao_followup ? ' — ' + esc(l.acao_followup) : ''}`
      : l.acao_followup ? `📋 ${esc(l.acao_followup)}` : null;
    const meta = [
      l.segmento ? `🏥 ${segLabel(l.segmento)}` : null,
      l.cidade ? `📍 ${esc(l.cidade)}` : null,
      phoneHtml,
      l.responsavel ? `👤 ${esc(l.responsavel)}` : null,
      proxPassoMeta,
    ].filter(Boolean);

    card.innerHTML = `
      <div class="lc-top">
        <span class="lc-name">${esc(l.nome) || '—'}</span>
        <div class="lc-badges">${l.status === 'novo' ? _novoBadgeBtn(l) : statusBadge(l.status)} ${temperaturaBadge(l)}</div>
      </div>
      ${meta.length ? `<div class="lc-meta">${meta.map(m => `<span class="lc-meta-item">${m}</span>`).join('')}</div>` : ''}
      ${msgBtnHtml ? `<div class="lc-msg-action">${msgBtnHtml}</div>` : ''}`;
    card.onclick = () => openLeadModal(l.lead_id);
    _bindCopyMsgBtns(card);
    _bindNovoBadgeBtns(card);
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
  state.temperatura = document.getElementById('filter-temperatura').value;
  state.page = 1;
  updateFilterChips();
  loadLeads();
}

function clearFilters() {
  state.status = '';
  state.segmento = '';
  state.temperatura = '';
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-segmento').value = '';
  document.getElementById('filter-temperatura').value = '';
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
    state.temperatura && { label: `Temp: ${state.temperatura}`, clear: () => { state.temperatura = ''; document.getElementById('filter-temperatura').value = ''; } },
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
  document.getElementById('historico-section').classList.toggle('hidden', isNew);

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
    loadHistorico(leadId);
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

async function loadHistorico(leadId) {
  const list = document.getElementById('historico-list');
  const count = document.getElementById('hist-count');
  const perfilEl = document.getElementById('perfil-comunicacao');
  list.innerHTML = '<div class="hist-loading">Carregando…</div>';
  try {
    const [resAtiv, resPerfil] = await Promise.all([
      fetch(`/api/leads/${leadId}/atividades`),
      fetch(`/api/leads/${leadId}/perfil`),
    ]);
    const ativs = resAtiv.ok ? await resAtiv.json() : [];
    const perfil = resPerfil.ok ? await resPerfil.json() : null;

    count.textContent = ativs.length ? `${ativs.length} eventos` : '';

    // Perfil de comunicação
    if (perfil && perfil.total_mensagens > 0) {
      perfilEl.style.display = '';
      perfilEl.innerHTML = renderPerfilComunicacao(perfil);
    } else {
      perfilEl.style.display = 'none';
    }

    if (!ativs.length) {
      list.innerHTML = '<div class="hist-empty">Nenhuma atividade registrada ainda.</div>';
      return;
    }
    list.innerHTML = ativs.map(a => renderHistItem(a)).join('');
  } catch {
    list.innerHTML = '<div class="hist-empty">Não foi possível carregar o histórico.</div>';
  }
}

function renderPerfilComunicacao(perfil) {
  const tipoEmoji = { audio: '🎙️', text: '💬', image: '🖼️', texto: '💬' };
  const tipoLabel = { audio: 'Áudio', text: 'Texto', image: 'Imagem', texto: 'Texto' };
  const chips = (perfil.tipos || []).map(t => {
    const emoji = tipoEmoji[t.tipo] || '📩';
    const label = tipoLabel[t.tipo] || t.tipo;
    const extra = t.tipo === 'audio' && t.duracao_total_s > 0
      ? ` · ${fmtAudioDur(t.duracao_total_s)}` : '';
    return `<span class="perfil-chip">${emoji} ${label} <strong>${t.total}</strong>${extra}</span>`;
  }).join('');
  const audioTotal = perfil.total_audio_s > 0
    ? `<span class="perfil-audio-total">Total em áudio: ${fmtAudioDur(perfil.total_audio_s)}</span>` : '';
  return `<div class="perfil-chips">${chips}</div>${audioTotal}`;
}

function fmtAudioDur(s) {
  if (!s) return '';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}min ${sec}s` : `${sec}s`;
}

function renderHistItem(a) {
  const data = a.data_hora ? a.data_hora.slice(0, 16).replace('T', ' ') : '—';
  const [datePart, timePart] = data.split(' ');
  const dateF = datePart ? datePart.split('-').reverse().join('/') : '—';
  const acao = esc(a.acao_executada || '');
  const resumo = esc(a.resumo || '');
  const tipo = a.tipo === 'audio' ? '🎙️' : a.tipo === 'image' ? '🖼️' : '💬';

  // Confiança IA — só exibe se existir e for relevante
  let confiancaBadge = '';
  if (a.confianca_ia !== null && a.confianca_ia !== undefined) {
    const pct = Math.round(a.confianca_ia * 100);
    const cls = a.confianca_ia >= 0.7 ? 'conf-alta' : a.confianca_ia >= 0.4 ? 'conf-media' : 'conf-baixa';
    confiancaBadge = `<span class="hist-conf ${cls}" title="Confiança da IA: ${pct}%">${pct}%</span>`;
  }

  // Duração de áudio
  let duracaoTag = '';
  if (a.tipo === 'audio' && a.duracao_audio_s) {
    duracaoTag = `<span class="hist-duracao">${fmtAudioDur(a.duracao_audio_s)}</span>`;
  }

  return `
    <div class="hist-item">
      <div class="hist-dot"></div>
      <div class="hist-content">
        <div class="hist-meta">
          <span class="hist-tipo">${tipo}</span>
          <span class="hist-data">${dateF}${timePart ? ' ' + timePart : ''}</span>
          ${duracaoTag}
          ${acao ? `<span class="hist-acao">${acao}</span>` : ''}
          ${confiancaBadge}
        </div>
        ${resumo ? `<div class="hist-resumo">${resumo}</div>` : ''}
      </div>
    </div>`;
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
  document.getElementById('f-temperatura').value = l.temperatura || 'frio';
  document.getElementById('f-data-recontato').value = (l.data_recontato || '').slice(0, 10);
  document.getElementById('f-whatsapp').value = l.whatsapp || '';
  document.getElementById('f-email').value = l.email || '';
  document.getElementById('f-instagram').value = l.instagram || '';
  document.getElementById('f-site').value = l.site || '';
  document.getElementById('f-responsavel').value = l.responsavel || '';
  document.getElementById('f-fonte').value = l.fonte || '';
  document.getElementById('f-followup').value = (l.proximo_followup_em || '').slice(0, 10);
  document.getElementById('f-acao-followup').value = l.acao_followup || '';
  document.getElementById('f-observacoes').value = l.observacoes || '';
  document.getElementById('f-valor-venda').value = l.valor_venda || '';
  document.getElementById('f-data-fechamento').value = (l.data_fechamento || '').slice(0, 10);
  document.getElementById('f-motivo-perda').value = l.motivo_perda || '';
  document.getElementById('f-data-criacao').value = (l.data_criacao || '').slice(0, 10);
  updateConditionalFields(l.status || 'novo');
  updateMsgSugerida(l);
  // Guarda o estado inicial pra rastrear conversão A/B
  state._modalStatusInicial = l.status || 'novo';
  state._modalSegmento = l.segmento || '';

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
  document.getElementById('fg-data-recontato').classList.toggle('hidden', !isPerdido);
  // Auto-set temperatura para cliente quando fechado
  if (isFechado) {
    document.getElementById('f-temperatura').value = 'cliente';
  }
}

function clearForm() {
  ['f-nome','f-cidade','f-whatsapp','f-email','f-instagram','f-site','f-responsavel',
   'f-acao-followup','f-observacoes','f-valor-venda','f-data-fechamento','f-motivo-perda',
   'f-data-criacao','f-data-recontato'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('f-segmento').value = '';
  document.getElementById('f-status').value = 'novo';
  document.getElementById('f-temperatura').value = 'frio';
  document.getElementById('f-fonte').value = '';
  document.getElementById('f-followup').value = '';
  updateConditionalFields('novo');
  document.getElementById('msg-sugerida-section')?.classList.add('hidden');
}

function formData() {
  return {
    nome: document.getElementById('f-nome').value.trim(),
    cidade: document.getElementById('f-cidade').value.trim(),
    segmento: document.getElementById('f-segmento').value,
    status: document.getElementById('f-status').value,
    temperatura: document.getElementById('f-temperatura').value,
    whatsapp: document.getElementById('f-whatsapp').value.trim(),
    email: document.getElementById('f-email').value.trim(),
    instagram: document.getElementById('f-instagram').value.trim(),
    site: document.getElementById('f-site').value.trim(),
    responsavel: document.getElementById('f-responsavel').value.trim(),
    fonte: document.getElementById('f-fonte').value,
    proximo_followup_em: document.getElementById('f-followup').value || '',
    acao_followup: document.getElementById('f-acao-followup').value.trim(),
    observacoes: document.getElementById('f-observacoes').value.trim(),
    valor_venda: document.getElementById('f-valor-venda').value || '',
    data_fechamento: document.getElementById('f-data-fechamento').value || '',
    motivo_perda: document.getElementById('f-motivo-perda').value.trim(),
    data_recontato: document.getElementById('f-data-recontato').value || '',
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

    // Rastrear conversão A/B: lead saiu de novo/contato feito para outro status
    if (!isNew && ['novo', 'contato feito'].includes(state._modalStatusInicial)) {
      const novoStatus = data.status;
      if (!['novo', 'contato feito'].includes(novoStatus)) {
        _trackAbEvento(leadId, state._modalSegmento, 'respondeu');
      }
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

// Copy button inside modal
document.getElementById('btn-copy-msg-modal')?.addEventListener('click', () => {
  const pre = document.getElementById('msg-sugerida-text');
  const btn = document.getElementById('btn-copy-msg-modal');
  const sec = document.getElementById('msg-sugerida-section');
  if (!pre || !btn) return;
  navigator.clipboard.writeText(pre.textContent).then(() => {
    btn.classList.add('copied');
    setTimeout(() => btn.classList.remove('copied'), 1400);
    const leadId = document.getElementById('form-lead-id').value;
    const segmento = document.getElementById('f-segmento').value;
    const tipo = sec?.dataset.msgTipo || 'inicial';
    _trackAbEvento(leadId, segmento, 'copiada', tipo);
  });
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

async function reativarAutoErro() {
  const btn = document.getElementById('btn-reativar');
  btn.disabled = true;
  btn.textContent = 'Reativando…';
  try {
    const res = await fetch('/api/leads/reativar-auto-erro', { method: 'POST' });
    const data = await res.json();
    if (data.reativados === 0) {
      alert('Nenhum lead bloqueado encontrado. Todos os leads "novo" já estão na fila.');
    } else {
      alert(`${data.reativados} lead(s) reativado(s)! Eles voltaram para a fila de envio automático.`);
    }
  } catch (e) {
    alert('Erro: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 Reativar fila';
  }
}

loadLeads();
