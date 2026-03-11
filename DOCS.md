# 📚 Documentação — IziProspect

Guia rápido para encontrar o que você precisa.

---

## 🎯 Começando

- **[BUILD_SUMMARY.md](./BUILD_SUMMARY.md)** — Visão geral do projeto, o que foi feito, stack técnico
- **[README.md](./README.md)** — Setup inicial, variáveis de ambiente, deploy

---

## 💬 CRM Conversacional

- **[CRM_CONVERSACIONAL.md](./CRM_CONVERSACIONAL.md)** — Micro-updates e queries por linguagem natural
  - Micro-updates: atualizar status com linguagem natural
  - Queries: consultar leads em tempo real
  - Padrões reconhecidos
  - Exemplos de uso

---

## 🎨 Dashboard web

- **[DASHBOARD.md](./DASHBOARD.md)** — Documentação completa do dashboard
  - Arquitetura
  - Features (stats, lista, CRUD, filters)
  - API endpoints
  - Mobile-first design
  - Database methods
  - Roadmap

### Botão Salvar no header do modal

O botão **Salvar** fica fixo no header do modal (ao lado do título), acessível sem scroll independente do tamanho do formulário. O rodapé contém apenas as ações secundárias (Cancelar, Deletar).

### Histórico de atividades no modal de lead

Ao abrir qualquer lead existente, o modal exibe uma seção **📋 Histórico** com a timeline completa de interações.

**Cada evento mostra:**
- Tipo: 💬 texto / 🎙️ áudio / 🖼️ imagem
- Data/hora
- Ação executada pela IA (`acao_executada`)
- Resumo da conversa
- **Confiança da IA** — badge colorido (🟢 ≥70% / 🟡 40–69% / 🔴 <40%)
- **Duração** — exibida para eventos de áudio (ex: `2min 30s`)

**Perfil de comunicação** (acima da timeline):
Resume como o lead se comunica — quantidade por tipo e total de áudio enviado. Carregado via `GET /api/leads/{id}/perfil`.

**Endpoints:**
- `GET /api/leads/{lead_id}/atividades` — até 30 atividades, mais recente primeiro
- `GET /api/leads/{lead_id}/perfil` — breakdown de tipos + duração total de áudio

**DB methods:**
- `db.get_lead_activities(lead_id)` — inclui `confianca_ia` e `duracao_audio_s`
- `db.get_perfil_comunicacao(lead_id)` — agrega por tipo

**URLs:**
- Local: `http://localhost:8000/dashboard` / `/leads`
- Produção: `https://iziprospect-production.up.railway.app/dashboard`

---

## 🌐 Landing Page

Página de marketing standalone — não usa o `base.html` (sem sidebar).

**URL:** `/landing`
**Arquivo:** `app/templates/landing.html`
**Rota:** `app/routers/dashboard_ui.py`

### Seções da landing (em ordem)
1. **Nav** — Logo + link "Planos" + CTA "Acessar plataforma"
2. **Hero** — Headline principal + mock de conversa + lead card animado
3. **Social proof bar** — 4 stats (100% capturado, 0 cliques, ∞ leads, 24h)
4. **Problema** — 3 pain cards (leads perdidos, CRM vazio, follow-ups que não acontecem)
5. **Analogia** — "Diário vs gravador que escreve sozinho"
6. **Como funciona** — 3 passos
7. **Features** — 6 cards de funcionalidades
8. **Dados** — "O ativo escondido" + visual de métricas
9. **Posicionamento** — "Você não compete com HubSpot, compete com o caos"
10. **Planos** — Starter vs Pro (ver abaixo)
11. **CTA final** — Botões de ação
12. **Footer**

### Planos (seção `#plans`)

| | Starter | Pro |
|---|---|---|
| **Nome** | Modo Grupo | Número Dedicado |
| **Como funciona** | Vendedor encaminha conversa pro grupo → IA organiza | WhatsApp Business conectado → captura automática |
| **Fluxo** | Conversa → Encaminha → IA organiza | Conversa → IA classifica → Relatório diário → Aprovação |
| **Cobertura** | O que for encaminhado | 100% do número |
| **Dependência humana** | Precisa encaminhar | Nenhuma |
| **Relatório diário** | Não | ✓ Incluso |
| **Setup** | Simples | Requer configuração |
| **Ideal para** | Vendedores solos, times pequenos, validação | Empresas com WhatsApp Business, times estruturados |

### Relatório diário de aprovação (Pro)

Feature exclusiva do plano Pro. Ao fim do dia, a IA apresenta o resumo de todas as conversas classificadas em 3 estados:

- `✓ Lead` — interesse real de compra identificado → já no pipeline
- `? Revisar` — contexto ambíguo → aguarda aprovação do usuário
- `✕ Ruído` — suporte, fornecedor, conversa irrelevante → descartado

O usuário revisa em ~2 minutos e aprova/descarta as sugestões. Pipeline limpo sem trabalho manual.

> **Status:** Definido no produto e na landing. Implementação pendente no backend.

### Acesso rápido via sidebar
O link "Landing Page" foi adicionado à sidebar do dashboard (`base.html`) e ao bottom nav mobile — abre em nova aba.

---

## 💰 Resultado de venda

- **[SALES_RESULT_DETECTION.md](./SALES_RESULT_DETECTION.md)** — Detecção automática de vendas
  - Indicadores de venda ganha/perdida
  - Como funciona
  - Exemplos de uso
  - Próximas fases

---

## 📋 Por tarefa

### "Como faço para..."

#### ...criar um novo lead?
→ Vá para `/leads`, clique no FAB (+), preencha e salve.

#### ...editar um lead existente?
→ Vá para `/leads`, clique no lead, edite e salve.

#### ...deletar um lead?
→ Abra o lead, clique "Deletar", confirme.

#### ...ver estatísticas do dia?
→ Vá para `/dashboard`, veja cards, gráficos, listas e alertas de pipeline.

#### ...identificar leads frios ou esquecidos?
→ No `/dashboard`, alertas aparecem automaticamente: ❄️ **Leads frios** (sem contato há 15+ dias) e 👻 **Nunca contatados** (status `novo` há 7+ dias sem nenhuma atividade).

#### ...saber o nível de engajamento de um lead?
→ Em `/leads`, cada card exibe o **Score de Engajamento** (Frio / Morno / Ativo / Quente / Fechando) calculado automaticamente com base em status, recência, prioridade e followup.

#### ...ver o desempenho da IA?
→ Vá para `/estatisticas` e role até a seção **Inteligência IA** (após a linha divisória). Mostra: mensagens processadas, confiança global, ações mais executadas, confiança por tipo de mensagem e fila de revisão (interpretações incertas <40%).

#### ...filtrar leads por status/segmento?
→ Em `/leads`, clique "Filtrar", selecione os critérios.

#### ...receber resumo diário no WhatsApp?
→ Configurado automaticamente para 18:30. Verifique `DEFAULT_TIMEZONE` no .env.

#### ...entender o que foi detectado de venda?
→ Leia [SALES_RESULT_DETECTION.md](./SALES_RESULT_DETECTION.md)

#### ...ver análises de conversa?
→ Vá para `/dashboard`, role down para "Análises de Conversa" (mostra distribuição de confiança).

#### ...importar 30 leads antigos via CSV?
→ Vá para `/leads`, clique em "Importar", cole seu CSV (separado por tab/semicolon/vírgula), e clique enviar.

#### ...atualizar um lead rapidamente no grupo?
→ Use micro-updates: "clinica sorriso respondeu", "mandei mensagem pra dr joao", "odonto prime quer demo".
→ Leia [CRM_CONVERSACIONAL.md — Micro-updates](./CRM_CONVERSACIONAL.md#micro-updates).

#### ...consultar leads no grupo (sem sair do WhatsApp)?
→ Use queries: "leads de hoje", "quem respondeu", "followup", "pipeline".
→ Leia [CRM_CONVERSACIONAL.md — Queries](./CRM_CONVERSACIONAL.md#queries).

---

## 🔧 Para desenvolvedores

### Estrutura do código

```
app/
├── routers/              # API + UI routes
│   ├── api_leads.py     # REST endpoints
│   └── dashboard_ui.py  # HTML pages
├── templates/           # Jinja2 templates
├── static/              # CSS + JS
├── services/            # Business logic
│   ├── crm_interpreter.py  # CRM message parsing + sales detection
│   │                       # + micro-updates + query detection
│   ├── db_service.py       # Database layer
│   │                       # + fuzzy matching + CRM queries
│   ├── openai_service.py   # OpenAI integration
│   ├── sheets_service.py   # Google Sheets sync
│   └── evolution_service.py # WhatsApp API
├── config.py            # Environment config
└── main.py              # FastAPI app + background loops
```

### Adicionar uma nova feature

1. **API endpoint** → `app/routers/api_leads.py`
2. **Database method** → `app/services/db_service.py`
3. **Frontend (JS)** → `app/static/leads.js` ou `dashboard.js`
4. **Template (HTML)** → `app/templates/leads.html` ou `dashboard.html`
5. **Styles** → `app/static/style.css`

### Rodar localmente

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
# Open http://localhost:8000/dashboard
```

### Deploy

```bash
git push origin claude/analyze-project-XnE4G
# Railway auto-detects, builds, deploys
```

---

## 📊 API Reference

Resumo dos endpoints:

### Dashboard stats
```
GET /api/stats
→ {
    by_status, by_segmento, by_prioridade,
    total_ativos, followups_vencidos, followups_hoje, criados_semana,
    leads_frios,            ← sem contato há 15+ dias
    leads_nunca_contatados, ← status 'novo' há 7+ dias, sem atividades
    recentes: [...],
    proximos_followups: [...]
  }

GET /api/analises/stats
→ { total, avg_confianca, distribuicao: {baixa, incerta, promissora, quase_certa}, recentes: [...] }
```

### Inteligência IA (motor de processamento — separado dos leads)
```
GET /api/ia/stats
→ {
    totais: {
      total_processadas,   ← total de mensagens processadas pela IA
      com_score,           ← quantas têm score de confiança
      confianca_global,    ← média global (0.0–1.0)
      baixa_confianca_count, ← interações com confiança < 40%
      total_audios,
      duracao_audio_media_s
    },
    top_acoes: [{acao, total}],           ← ações mais executadas pela IA
    confianca_por_tipo: [{tipo, total,    ← confiança média por tipo de msg
                          confianca_media, confianca_min, confianca_max}],
    volume_por_dia: [{dia, total,         ← volume de processamento 30 dias
                      confianca_media}],
    baixa_confianca: [...]               ← últimas 10 interações <40% para revisão
  }
```

### Perfil de comunicação do lead
```
GET /api/leads/{lead_id}/perfil
→ {
    tipos: [{tipo, total, duracao_total_s, confianca_media}],
    total_mensagens: int,
    total_audio_s: float   ← segundos totais de áudio enviados pelo lead
  }
```

### Bulk import
```
POST /api/leads/bulk
Body: { leads: [{nome*, cidade, email, ...}, ...] }
→ { ok, total, imported, needs_review, errors, leads, review, failed }
```

### Leads CRUD
```
GET /api/leads?status=novo&search=clinica&page=1
→ { leads: [...], total: int, page: int, page_size: int }

GET /api/leads/{lead_id}
→ { lead_id, nome, cidade, ... }

GET /api/leads/{lead_id}/atividades
→ [{ data_hora, tipo, canal, acao_executada, resumo, confianca_ia, duracao_audio_s }]

POST /api/leads
Body: { nome*, cidade, segmento, whatsapp, ... }
→ { lead_id: "L0042", ok: true }

PUT /api/leads/{lead_id}
Body: { status: "fechado", observacoes: "...", ... }
→ { ok: true }

DELETE /api/leads/{lead_id}
→ { ok: true }
```

Veja [DASHBOARD.md — API](./DASHBOARD.md#rest-api) para detalhes completos.

---

## 🎛️ Configuração

### Environment variables essenciais

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# PostgreSQL
DATABASE_URL=postgresql://user:pass@host:5432/iziprospect

# Google Sheets
GOOGLE_SHEETS_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON=...

# WhatsApp / Evolution
CRM_TARGET_GROUP_ID=...
EVOLUTION_API_URL=...
EVOLUTION_API_KEY=...

# Dashboard
DEFAULT_TIMEZONE=America/Sao_Paulo
DAILY_SUMMARY_HOUR=18
DAILY_SUMMARY_MINUTE=30
```

Veja [DASHBOARD.md — Configuração](./DASHBOARD.md#-configuração) para a lista completa.

---

## 🐛 Troubleshooting

| Problema | Verificar | Solução |
|----------|-----------|---------|
| Dashboard não carrega | `curl /health` | Check if server is running |
| Leads não aparecem | DB connection | Verify DATABASE_URL |
| API retorna 500 | Logs do servidor | Check console for errors |
| Daily summary não chega | `DISABLE_DAILY_SUMMARY` | Must be `false` |
| Resultado de venda não detecta | Keywords | Check `detect_sales_result()` function |

---

## 📈 Roadmap

### ✅ Completo (Fase 1)
- Dashboard com stats e gráficos
- CRUD de leads
- Mobile-first design
- Daily summary
- Detecção de venda

### ✅ Completo (Fase 1.5)
- Análises de conversa com persistência (score 1-10)
- Dashboard analytics com distribuição de confiança
- Bulk import de leads via CSV
- Bug fixes: word boundaries, JSON error handling

### ✅ Completo (Fase 1.6)
- Micro-updates conversacionais (atualizar lead por padrão verbal)
- Queries conversacionais (consultar leads no WhatsApp)
- Fuzzy matching por nome sem criar lead novo

### ✅ Completo (Fase 1.7 — Landing + Produto)
- Landing page completa com todas as seções de marketing
- Definição dos 2 planos: Starter (Modo Grupo) e Pro (Número Dedicado)
- Seção de planos com cards, comparativo e tabela na landing
- Relatório diário de aprovação definido como feature exclusiva do Pro
- Landing page acessível via sidebar do dashboard

### ✅ Completo (Fase 1.8 — Aproveitamento de dados + UX)
- **UX:** Botão Salvar fixo no header do modal (sem precisar de scroll)
- **Alertas de pipeline:** cards automáticos no dashboard para leads frios (15+ dias) e nunca contatados (7+ dias em `novo` sem atividade)
- **Score de engajamento:** badge Frio/Morno/Ativo/Quente/Fechando calculado client-side em cada card de lead
- **Histórico enriquecido:** confiança da IA (badge colorido) e duração de áudio em cada evento
- **Perfil de comunicação:** resumo de tipos (áudio/texto/imagem) e total de áudio por lead, exibido no topo do histórico
- **Painel Inteligência IA** em `/estatisticas`: seção dedicada ao motor de processamento (separada dos dados de leads) com KPIs do motor, top ações executadas, confiança por tipo de mensagem e fila de revisão de interpretações incertas
- **APIs novas:** `GET /api/ia/stats` e `GET /api/leads/{id}/perfil`

### 🔄 Planejado (Fase 2)
- Follow-up automático
- Tags customizadas
- Bulk actions (update múltiplos leads)
- **Relatório diário de aprovação** (backend — já definido no produto)
- Modo Número Dedicado (conectar WhatsApp Business via Evolution API)

### 🚀 Futuro (Fase 3+)
- Analytics avançado
- Multi-user
- App mobile
- Faturamento integrado

Veja [DASHBOARD.md — Roadmap](./DASHBOARD.md#-próximas-features-planejadas-roadmap) para detalhes.

---

## 📞 Quick links

- **Código:** https://github.com/Drinhoc/iziprospect (branch `claude/analyze-project-XnE4G`)
- **Servidor:** https://iziprospect-production.up.railway.app/
- **Dashboard:** https://iziprospect-production.up.railway.app/dashboard
- **Leads:** https://iziprospect-production.up.railway.app/leads

---

## 📚 Documentos principais

| Documento | Para quem | O que contém |
|-----------|----------|--------------|
| [BUILD_SUMMARY.md](./BUILD_SUMMARY.md) | Todos | Overview do projeto, decisões |
| [DASHBOARD.md](./DASHBOARD.md) | Devs + PMs | Detalhes completos do dashboard |
| [SALES_RESULT_DETECTION.md](./SALES_RESULT_DETECTION.md) | Devs + Sales | Como detectar venda ganha/perdida |
| [CRM_CONVERSACIONAL.md](./CRM_CONVERSACIONAL.md) | Todos | Micro-updates e queries por linguagem natural |
| [DOCS.md](./DOCS.md) | Todos | Este arquivo — índice |
| [README.md](./README.md) | Devs | Setup, deploy, variáveis |

---

**Última atualização:** 2026-03-11 (Fase 1.8 — Aproveitamento de dados + Inteligência IA + UX)
