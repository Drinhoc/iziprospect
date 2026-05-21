/* conversa.js — MVP 2.0: visualização e interação com uma conversa do inbox */

let conversaData = null;
let isSending = false;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  loadConversa();
  // Atualiza a conversa a cada 15s para capturar novas mensagens
  setInterval(loadConversa, 15000);
});

// ---------------------------------------------------------------------------
// Carrega conversa
// ---------------------------------------------------------------------------

async function loadConversa() {
  try {
    const data = await fetch(`/api/inbox/conversas/${CONVERSA_ID}`).then(r => r.json());
    conversaData = data.conversa;
    renderConversa(data.conversa, data.mensagens);
  } catch (e) {
    console.error('loadConversa error:', e);
  }
}

function renderConversa(conv, mensagens) {
  // Header
  const nome = conv.nome_contato || conv.numero || 'Desconhecido';
  document.getElementById('conv-nome').textContent   = nome;
  document.title = `${nome} — Inbox`;
  document.getElementById('conv-numero').textContent = conv.numero || conv.jid || '';
  document.getElementById('conv-ultima-msg').textContent = conv.ultimo_msg_em
    ? `última mensagem ${timeAgo(conv.ultimo_msg_em)}`
    : '';

  // Botões de ação baseados no status
  const btnResolver = document.getElementById('btn-resolver');
  const btnArquivar = document.getElementById('btn-arquivar');
  const btnReabrir  = document.getElementById('btn-reabrir');
  if (conv.status === 'aberto') {
    btnResolver.classList.remove('hidden');
    btnArquivar.classList.remove('hidden');
    btnReabrir.classList.add('hidden');
  } else {
    btnResolver.classList.add('hidden');
    btnArquivar.classList.add('hidden');
    btnReabrir.classList.remove('hidden');
  }

  // Caixa de resposta só aparece para conversas abertas
  document.getElementById('reply-box').style.display = conv.status === 'aberto' ? '' : 'none';

  // Badges
  renderBadges(conv);

  // Resumo IA
  const resumoEl = document.getElementById('conv-resumo-ia');
  resumoEl.textContent = conv.resumo_ia || 'Ainda sem análise. Clique em "Re-analisar" para gerar.';

  // Confiança IA
  const confEl = document.getElementById('conv-confianca');
  if (conv.confianca_ia > 0) {
    const emoji = conv.confianca_ia >= 7 ? '🟢' : conv.confianca_ia >= 4 ? '🟡' : '🔴';
    confEl.textContent = `${emoji} Confiança: ${conv.confianca_ia}/10`;
  } else {
    confEl.textContent = '';
  }

  // Sugestão de resposta
  const suggEl  = document.getElementById('reply-suggestion');
  const suggTxt = document.getElementById('reply-suggestion-text');
  if (conv.resposta_sugerida && conv.status === 'aberto') {
    suggTxt.textContent = conv.resposta_sugerida;
    suggEl.classList.remove('hidden');
  } else {
    suggEl.classList.add('hidden');
  }

  // Selects de classificação
  setSelectValue('conv-categoria', conv.categoria || 'outro');
  setSelectValue('conv-prioridade', conv.prioridade || 'normal');

  // Lead vinculado
  const leadEl = document.getElementById('conv-lead-info');
  if (conv.lead_id) {
    leadEl.innerHTML = `<a href="/leads" class="conv-lead-link">Ver lead ${escHtml(conv.lead_id)}</a>`;
  } else {
    leadEl.innerHTML = '<span class="text-muted">Nenhum lead vinculado</span>';
  }

  // Thread de mensagens
  renderThread(mensagens);
}

function renderBadges(conv) {
  const el = document.getElementById('conv-badges');
  const parts = [];

  if (conv.status !== 'aberto') {
    parts.push(`<span class="conv-badge conv-badge--status conv-badge--${conv.status}">${conv.status}</span>`);
  }
  if (conv.prioridade && conv.prioridade !== 'normal') {
    parts.push(`<span class="conv-badge conv-badge--prio conv-badge--${conv.prioridade}">${conv.prioridade}</span>`);
  }
  if (conv.categoria && conv.categoria !== 'outro') {
    parts.push(`<span class="conv-badge conv-badge--cat">${conv.categoria}</span>`);
  }

  el.innerHTML = parts.join('');
}

function renderThread(mensagens) {
  const thread = document.getElementById('conversa-thread');
  if (!mensagens || mensagens.length === 0) {
    thread.innerHTML = '<div class="thread-empty">Nenhuma mensagem registrada.</div>';
    return;
  }

  let html = '';
  let lastDate = '';
  for (const m of mensagens) {
    const dt = m.enviado_em ? new Date(m.enviado_em) : null;
    const dateStr = dt ? dt.toLocaleDateString('pt-BR') : '';
    if (dateStr && dateStr !== lastDate) {
      html += `<div class="thread-date-sep">${dateStr}</div>`;
      lastDate = dateStr;
    }
    html += renderMensagem(m);
  }

  thread.innerHTML = html;
  // Scroll to bottom
  thread.scrollTop = thread.scrollHeight;
}

function renderMensagem(m) {
  const deMe = m.de_mim;
  const cls  = deMe ? 'msg msg--saida' : 'msg msg--entrada';
  const hora = m.enviado_em ? new Date(m.enviado_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';

  let conteudo = '';
  if (m.tipo === 'audio') {
    const texto = m.transcricao || m.texto;
    conteudo = texto
      ? `<div class="msg-audio-badge">🎤 Áudio</div><div class="msg-transcricao">${escHtml(texto)}</div>`
      : `<div class="msg-audio-badge">🎤 Áudio <span class="msg-sem-transcricao">(sem transcrição)</span></div>`;
  } else if (m.tipo === 'image') {
    conteudo = `<div class="msg-midia-badge">🖼️ Imagem</div>`;
  } else if (m.tipo === 'document') {
    conteudo = `<div class="msg-midia-badge">📄 Documento</div>`;
  } else {
    conteudo = `<div class="msg-text">${escHtml(m.texto || '')}</div>`;
  }

  return `
    <div class="${cls}">
      <div class="msg-bubble">
        ${conteudo}
        <span class="msg-hora">${hora}</span>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Ações
// ---------------------------------------------------------------------------

async function resolverConversa() {
  if (!confirm('Marcar esta conversa como resolvida?')) return;
  try {
    await fetch(`/api/inbox/conversas/${CONVERSA_ID}/resolver`, { method: 'POST' });
    await loadConversa();
  } catch (e) { alert('Erro: ' + e.message); }
}

async function arquivarConversa() {
  if (!confirm('Arquivar esta conversa?')) return;
  try {
    await fetch(`/api/inbox/conversas/${CONVERSA_ID}/arquivar`, { method: 'POST' });
    await loadConversa();
  } catch (e) { alert('Erro: ' + e.message); }
}

async function reabrirConversa() {
  try {
    await fetch(`/api/inbox/conversas/${CONVERSA_ID}/reabrir`, { method: 'POST' });
    await loadConversa();
  } catch (e) { alert('Erro: ' + e.message); }
}

async function reanalisarConversa() {
  const btn = document.querySelector('.btn-reanalisar');
  btn.disabled = true;
  btn.textContent = 'Analisando…';
  try {
    const data = await fetch(`/api/inbox/conversas/${CONVERSA_ID}/analisar`, { method: 'POST' }).then(r => r.json());
    if (data && conversaData) {
      Object.assign(conversaData, data);
      renderBadges(conversaData);
      document.getElementById('conv-resumo-ia').textContent = data.resumo_ia || 'Sem análise.';
      if (data.confianca_ia > 0) {
        const emoji = data.confianca_ia >= 7 ? '🟢' : data.confianca_ia >= 4 ? '🟡' : '🔴';
        document.getElementById('conv-confianca').textContent = `${emoji} Confiança: ${data.confianca_ia}/10`;
      }
      if (data.resposta_sugerida) {
        document.getElementById('reply-suggestion-text').textContent = data.resposta_sugerida;
        document.getElementById('reply-suggestion').classList.remove('hidden');
      }
    }
  } catch (e) {
    alert('Erro ao analisar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.35"/></svg> Re-analisar`;
  }
}

async function updateField(field, value) {
  try {
    await fetch(`/api/inbox/conversas/${CONVERSA_ID}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    });
  } catch (e) { console.error('updateField error:', e); }
}

// ---------------------------------------------------------------------------
// Resposta
// ---------------------------------------------------------------------------

function useSuggestion() {
  const sugg = document.getElementById('reply-suggestion-text').textContent;
  document.getElementById('reply-text').value = sugg;
  document.getElementById('reply-text').focus();
}

function handleReplyKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    sendReply();
  }
}

async function sendReply() {
  if (isSending) return;
  const text = document.getElementById('reply-text').value.trim();
  if (!text) return;

  isSending = true;
  const btn = document.getElementById('reply-send-btn');
  btn.disabled = true;

  try {
    const res = await fetch(`/api/inbox/conversas/${CONVERSA_ID}/responder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json();
      alert('Erro ao enviar: ' + (err.detail || res.statusText));
      return;
    }
    document.getElementById('reply-text').value = '';
    await loadConversa();
  } catch (e) {
    alert('Erro de conexão: ' + e.message);
  } finally {
    isSending = false;
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function timeAgo(isoStr) {
  try {
    const diff = Date.now() - new Date(isoStr).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'agora';
    if (m < 60) return `${m} min atrás`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h atrás`;
    const d = Math.floor(h / 24);
    return `${d}d atrás`;
  } catch { return ''; }
}

function setSelectValue(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
