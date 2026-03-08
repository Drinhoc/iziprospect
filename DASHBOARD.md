# Dashboard Web — IziProspect

## 📋 Visão geral

O **IziProspect Dashboard** é uma interface web moderna e mobile-first para gerenciar leads de prospecção. Integrada ao FastAPI existente, oferece visualização em tempo real, CRUD completo de leads, filtros avançados e um resumo diário automático enviado via WhatsApp.

**URLs no servidor:**
- `https://iziprospect-production.up.railway.app/` → redireciona pro dashboard
- `https://iziprospect-production.up.railway.app/dashboard` → estatísticas e resumos
- `https://iziprospect-production.up.railway.app/leads` → lista de leads + CRUD

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│ FastAPI (port 8000)                                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  UI Routes (Jinja2 templates)                           │
│  ├─ GET /                    → redirect /dashboard      │
│  ├─ GET /dashboard           → dashboard.html           │
│  └─ GET /leads               → leads.html               │
│                                                          │
│  REST API Routes                                        │
│  ├─ GET /api/stats           → JSON stats               │
│  ├─ GET /api/leads           → paginated leads + filters│
│  ├─ GET /api/leads/{id}      → single lead              │
│  ├─ POST /api/leads          → create lead              │
│  ├─ PUT /api/leads/{id}      → update lead              │
│  └─ DELETE /api/leads/{id}   → delete lead (hard)       │
│                                                          │
│  Static Files (served from /static)                     │
│  ├─ style.css                → mobile-first CSS         │
│  ├─ dashboard.js             → stats + charts JS        │
│  └─ leads.js                 → CRUD + filtering JS      │
│                                                          │
│  Background Tasks                                       │
│  ├─ Sheets ↔ DB sync loop    → every 15 min            │
│  └─ Daily summary loop       → configurable time        │
│                                                          │
└─────────────────────────────────────────────────────────┘
         │
         ▼
    PostgreSQL (primary)
    └─ leads table
       └─ atividades table

    Google Sheets (mirror)
    └─ LEADS sheet
    └─ ATIVIDADES sheet
    └─ REVISAR sheet
```

---

## ✨ Features implementadas

### 1. **Dashboard — Estatísticas em tempo real** (`/dashboard`)

**Stat Cards (topo):**
- Total de leads ativos
- Follow-ups vencidos
- Follow-ups agendados para hoje
- Novos leads criados esta semana

**Gráficos de barras (CSS puro, sem biblioteca):**
- **Pipeline**: distribuição por status (novo → em contato → qualificado → proposta → negociando → fechado)
- **Segmento**: contagem por tipo (odonto, estética, médica, nutrição, fisio, outro)
- **Prioridade**: alta / média / baixa

**Listas dinâmicas:**
- Últimos 5 leads adicionados (com datas)
- Próximos 5 follow-ups pendentes (ordenados por data)

**Auto-refresh:**
- Dados recarregam a cada 2 minutos
- Timestamp de última atualização exibido

### 2. **Lista de Leads com CRUD completo** (`/leads`)

**Mobile (card list):**
- Cada card exibe: nome, badges de status/prioridade, cidade, segmento, telefone, próximo follow-up, pendência
- Tap no card abre o modal de edição

**Desktop (table):**
- Tabela com todas as colunas relevantes
- Click na linha abre modal
- Responsiva, com horizontal scroll se necessário

**Busca em tempo real:**
- Input com debounce de 350ms
- Busca em: nome, cidade, responsável, WhatsApp
- Resultado instantâneo na tabela/cards

**Filtros avançados:**
- Status (novo, em contato, qualificado, proposta, negociando, fechado, perdido, sem resposta)
- Segmento (odonto, estética, médica, nutrição, fisio, outro)
- Prioridade (alta, média, baixa)
- Combinados: A AND B AND C
- Filtros ativos exibidos como "chips" com opção de remover

**Paginação:**
- 50 leads por página (configurável via API)
- Botões Anterior/Próxima
- Indicador de página atual / total

**FAB (Floating Action Button):**
- No mobile: botão redondo fixo no canto inferior direito
- No desktop: fica visível mas em posição apropriada
- Abre modal para criar novo lead

**Modal/Bottom Sheet (CRUD):**

**Mobile (bottom sheet):**
- Slide up de baixo
- Handle visual no topo
- Ocupa 90% da altura da tela
- Scroll interno para formulário longo

**Desktop (centered modal):**
- Modal centralizado
- Overlay escuro ao fundo

**Campos editáveis:**
- Nome/Clínica* (obrigatório)
- Cidade, Segmento
- WhatsApp (normalizado automaticamente)
- E-mail, Instagram, Site
- Responsável, Fonte (cold, referral, instagram, event)
- Status, Prioridade
- Próximo follow-up (date picker)
- Pendência, Observações

**Campos somente-leitura (ao editar):**
- Lead ID (L0001, L0002, etc.)
- Resumo IA (gerado automaticamente)
- Criado em, Última interação

**Ações:**
- Salvar (POST para novo, PUT para editar)
- Cancelar
- Deletar (hard delete com confirmação — "Deletar "{nome}" permanentemente?")

### 3. **API REST**

#### `GET /api/stats`
Retorna JSON com dados para o dashboard:
```json
{
  "by_status": { "novo": 5, "em contato": 12, ... },
  "by_segmento": { "odonto": 20, "estética": 8, ... },
  "by_prioridade": { "alta": 3, "media": 15, "baixa": 10 },
  "total_ativos": 28,
  "followups_vencidos": 2,
  "followups_hoje": 5,
  "criados_semana": 12,
  "recentes": [ { "lead_id": "L0001", "nome": "...", ... }, ... ],
  "proximos_followups": [ ... ]
}
```

#### `GET /api/leads?status=novo&segmento=odonto&search=clinica&page=1&page_size=50`
Retorna lista paginada com filtros:
```json
{
  "leads": [ ... full lead objects ... ],
  "total": 156,
  "page": 1,
  "page_size": 50
}
```

#### `GET /api/leads/{lead_id}`
Retorna um lead específico (completo com todos os campos).

#### `POST /api/leads`
Cria um novo lead. Body:
```json
{
  "nome": "Clínica Sorriso",
  "cidade": "São Paulo",
  "segmento": "odonto",
  "status": "novo",
  "prioridade": "media",
  "whatsapp": "+55 11 99999-9999",
  "email": "contato@clinica.com",
  "instagram": "@clinica",
  "site": "clinica.com.br",
  "responsavel": "Dr. João",
  "fonte": "cold",
  "proximo_followup_em": "2026-03-15",
  "pendencia": "Enviar proposta",
  "observacoes": "..."
}
```
Retorna: `{ "lead_id": "L0042", "ok": true }`

#### `PUT /api/leads/{lead_id}`
Atualiza um lead. Apenas campos fornecidos são atualizados (merge).

#### `DELETE /api/leads/{lead_id}`
Deleta permanentemente o lead e suas atividades do banco.
Retorna: `{ "ok": true }`

### 4. **Análises de Conversa — Dashboard Analytics** (NEW)

**O que é:**
- Persistência e agregação de análises de conversa geradas pelo comando `ANALISAR:`
- Dashboard section com estatísticas em tempo real
- Distribuição de confiança em 4 tiers com emoji
- Histórico das últimas análises

**Dados coletados:**
- `confianca_analise`: score 1-10 da conversa (salvo em `atividades.confianca_analise`)
- `proximo_passo`: recomendação do bot (salvo em `leads.pendencia`)
- Resumo da conversa e contexto do lead

**Estatísticas no dashboard:**
```
Total de análises: 12
Confiança média: 6.4/10

Distribuição:
🔴 Baixa (1-3): 2 análises
🟡 Incerta (4-6): 4 análises
🟢 Promissora (7-8): 5 análises
💚 Quase certa (9-10): 1 análise

Últimas análises:
💚 9/10 - Clínica Sorriso — "Cliente confirmou interesse"
🟢 7/10 - OdontoVida — "Pediu proposta..."
🟡 5/10 - Studio Estética — "Conversação ok mas indeciso"
```

**API:** `GET /api/analises/stats`
- Retorna: total, avg_confianca, distribuicao (4 buckets), recentes (últimas 5)
- Endpoint integrado ao dashboard.js para refresh automático

---

### 5. **Daily Summary — Resumo automático via WhatsApp**

**O que é:**
- Loop em background que envia um resumo automático do dia no grupo CRM
- Horário configurável (padrão: 18:30)
- Só envia se houve atividade (zero spam em dias inativos)

**Conteúdo da mensagem:**
```
. 📊 Resumo do dia

Leads novos: 3
Interações: 7
Follow-ups agendados: 2

Últimas atividades:
• Clínica Sorriso — pediu proposta
• Mercado Oliveira — ligação realizada
• João Imóveis — reunião marcada
+4 atividades

📅 Follow-ups amanhã: 3

📈 Sequência ativa: 5 dias
```

**Regras:**
- Começa com `.` para passar no filtro anti-loop do bot
- Sequência ativa: conta dias consecutivos com ≥1 atividade (mostra se ≥2 dias)
- Se não houver atividade: não envia nada
- Se houver muitas atividades: mostra top 5 + "+N atividades"
- Sempre no mesmo horário, todo dia (cria ritual)

**Variáveis de ambiente:**
```
DAILY_SUMMARY_HOUR=18           # hora (0-23)
DAILY_SUMMARY_MINUTE=30         # minuto (0-59)
DISABLE_DAILY_SUMMARY=false     # desativa se true
DEFAULT_TIMEZONE=America/Sao_Paulo  # timezone para "hoje"
```

---

## 📱 Design — Mobile-first

**Decisões de design:**

1. **Bottom navigation bar (mobile):**
   - Fixa no rodapé
   - Dois links: Dashboard | Leads
   - Padrão nativo de apps
   - Safe area insets para notch/home bar

2. **Sidebar (desktop):**
   - Fixa à esquerda (240px)
   - Logo com ícone
   - Navegação
   - Hidden em < 768px

3. **Cards em vez de tabela (mobile):**
   - Evita scroll horizontal (péssimo no celular)
   - Informação densa mas legível
   - Uma interação por card (tap = editar)

4. **Modal/bottom sheet:**
   - Mobile: slide up de baixo, 90% altura
   - Desktop: centered overlay
   - Handle visual, smooth animations

5. **Touch targets mínimos:**
   - Todos os buttons/inputs: ≥ 44px de altura
   - Gaps apropriados entre elementos
   - Fonte mínima 16px (evita zoom automático no iOS)

6. **FAB (Floating Action Button):**
   - Mobile: canto inferior direito, acima do bottom nav
   - Desktop: mesmo lugar mas menos no caminho
   - Ação: novo lead

7. **Cores e badges:**
   - Status: cores claras e distinguíveis
   - Prioridade: red (alta) / amber (média) / green (baixa)
   - Sem dependência de cor só (acessibilidade)

**CSS:**
- Totalmente custom, zero framework externo
- Mobile-first: CSS base é mobile, @media (min-width: 768px) para desktop
- Variables CSS para cores, espaçamentos, shadows
- Smooth transitions e animations

---

## 🗄️ Banco de dados — Novos métodos

### `db_service.py`

#### `get_stats(tz_name: str) -> Dict`
Retorna estatísticas agregadas para o dashboard:
- Contagens por status, segmento, prioridade
- Total ativo, vencidos, hoje, semana
- Top 5 recentes + top 5 follow-ups próximos

#### `list_leads(status, segmento, prioridade, search, page, page_size) -> Dict`
Retorna leads paginados com filtros opcionais:
- Filters aplicados com AND lógico
- Busca em nome, cidade, responsavel, whatsapp
- Ordenação por última interação DESC
- Retorna `{ "leads": [...], "total": int, "page": int, "page_size": int }`

#### `create_lead_from_dashboard(data: Dict) -> str`
Cria lead novo a partir do input do dashboard:
- Normaliza telefone
- Calcula campos derivados (nome_normalizado, cidade_normalizada, lead_key)
- Retorna `lead_id` gerado (L0001, L0002, etc.)

#### `update_lead_from_dashboard(lead_id: str, data: Dict) -> bool`
Atualiza lead com campos do dashboard:
- Permite: nome, cidade, segmento, whatsapp, email, instagram, site, responsavel, fonte, status, prioridade, observacoes, proximo_followup_em, **pendencia**
- Recalcula campos derivados se nome/cidade mudarem

#### `delete_lead(lead_id: str) -> bool`
Hard-deletes um lead e suas atividades:
- `DELETE FROM atividades WHERE lead_id = %s`
- `DELETE FROM leads WHERE lead_id = %s`

#### `get_daily_summary(tz_name: str) -> Optional[Dict]`
Busca dados para resumo diário:
- Retorna `None` se sem atividade (não envia msg)
- Calcula: leads_novos, interacoes, followups_hoje, ultimas_atividades, followups_amanha, streak_dias
- Usa timezone para calcular "hoje" e "amanhã"

---

## ⚙️ Configuração

### Environment Variables (`.env`)

```bash
# Existentes
OPENAI_API_KEY=sk-...
GOOGLE_SHEETS_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON=...
EVOLUTION_WEBHOOK_SECRET=...
EVOLUTION_API_URL=...
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE_NAME=...
CRM_TARGET_GROUP_ID=...
DATABASE_URL=postgresql://...
DEFAULT_TIMEZONE=America/Sao_Paulo

# Sheets sync
SHEETS_SYNC_INTERVAL_MINUTES=15

# Daily summary (NOVO)
DAILY_SUMMARY_HOUR=18
DAILY_SUMMARY_MINUTE=30
DISABLE_DAILY_SUMMARY=false
```

### Rotas FastAPI

**App structure:**
```
app/
├── routers/
│   ├── __init__.py
│   ├── api_leads.py          # REST API endpoints
│   └── dashboard_ui.py       # HTML routes (Jinja2)
├── templates/
│   ├── base.html             # Layout base + nav
│   ├── dashboard.html        # Stats page
│   └── leads.html            # Leads CRUD page
├── static/
│   ├── style.css             # Mobile-first CSS (~900 linhas)
│   ├── dashboard.js          # Stats + charts JS
│   └── leads.js              # CRUD + filtering JS (~400 linhas)
└── main.py                   # FastAPI app, background loops
```

**Mount points:**
- `StaticFiles("/static", "app/static")` em `app.mount("/static", ...)`
- Templates: `Jinja2Templates(directory="app/templates")`

---

## 🎯 Próximas features planejadas (Roadmap)

### V2 — Automação inteligente
- [ ] Follow-up automático: se follow-up vencido + sem resposta há 3 dias, sugerir ação
- [ ] Lead score automático baseado em atividade + tempo
- [ ] Tags customizadas por usuário
- [ ] Bulk actions (mudar status de múltiplos leads)

### V3 — Analytics & reporting
- [ ] Resumo semanal (segunda-feira)
- [ ] Gráfico de conversão: novo → qualificado → proposta → fechado
- [ ] Taxa de resposta por segmento
- [ ] Tempo médio de venda (lead → fechado)
- [ ] Ranking de vendedores (por interações, leads novos)

### V4 — Vendas (result tracking)
- [ ] Registrar resultado: ganho/perdido
- [ ] Valor de venda
- [ ] Data de fechamento
- [ ] Comissão calculada (+ Stripe/PayPal API)
- [ ] Dashboard de vendas fechadas

### V5 — Multi-user & permissões
- [ ] Usuários com diferentes roles (vendedor, gerente, admin)
- [ ] Leads atribuídos a vendedor específico
- [ ] Histórico de quem editou quê
- [ ] Restrições de acesso

### V6 — Mobile app nativa
- [ ] React Native ou Flutter
- [ ] Acesso offline (sincroniza quando volta online)
- [ ] Notificações push para follow-ups

---

## 🚀 Como usar

### **1. Acessar o dashboard**
```
http://localhost:8000/dashboard    (local)
https://iziprospect-production.up.railway.app/dashboard  (produção)
```

### **2. Ver lista de leads**
```
http://localhost:8000/leads
```

### **3. Criar lead via interface**
- Clique no botão FAB (+ redondo)
- Preencha nome, cidade, segmento (obrigatório: nome)
- Clique "Salvar"
- Lead é criado com ID sequencial (L0001, L0002, etc.)

### **4. Editar lead**
- Clique no card (mobile) ou linha (desktop)
- Faça alterações
- Clique "Salvar"

### **5. Deletar lead**
- Abra o modal de edição
- Clique "Deletar"
- Confirme a exclusão
- Lead é removido permanentemente do banco e do Sheets

### **6. Filtrar leads**
- Clique "Filtrar"
- Selecione status, segmento, prioridade
- Filtros aparecem como chips, clique para remover
- Busque por nome/cidade/responsavel no input de busca

### **7. Ver estatísticas**
- Vá para `/dashboard`
- Cards mostram totais do dia/semana
- Gráficos mostram distribuição por status/segmento/prioridade
- Listas mostram leads recentes e follow-ups próximos

### **8. Resumo diário automático**
- Chega no grupo WhatsApp todos os dias às 18:30 (configurável)
- Mostra: leads novos, interações, follow-ups, sequência ativa
- Apenas se houver atividade naquele dia

---

## 🔧 Decisões técnicas

### **1. Por que hard delete e não soft delete?**
- Soft delete (status='arquivado') era confuso na UI
- Hard delete é mais direto e profissional
- Atividades relacionadas são deletadas também (cascata)

### **2. Por que Jinja2 templates ao invés de SPA puro?**
- Renderização server-side para HTML inicial (mais rápido)
- APIs retornam JSON para dados dinâmicos
- Melhor SEO (não que importe aqui, mas bom padrão)
- Simples de manter

### **3. CSS custom sem framework?**
- Zero dependências externas
- Arquivo smaller (~15KB gzip)
- Controle total sobre mobile breakpoints
- Nenhum CSS não-utilizado

### **4. Por que streak (sequência ativa)?**
- Não é gamificação infantil — é feedback profissional
- Psicologicamente aumenta retenção (rituais de produtividade)
- Mostra consistência sem pressão
- Só aparece a partir de 2 dias (não fica ruído)

### **5. Por que daily summary deve ser automática?**
- Cria ritual: usuário espera a mensagem todos os dias
- Motivação: vê progresso do dia
- Sem ação: dispara insights de atividade perdida
- Via WhatsApp: já está no seu flow de trabalho

### **6. Timezone handling (zoneinfo):**
- Python 3.9+ tem `zoneinfo` built-in (sem pytz)
- Suporta IANA timezone names ("America/Sao_Paulo")
- Correto para daylight saving time
- "Hoje" é calculado no timezone do usuário, não em UTC

---

## 📊 Métricas & KPIs (futuros)

Uma vez que o dashboard estiver consolidado, acompanhe:

```
Diagnóstico do pipeline:
├─ Taxa de conversão: leads novos → qualificados
├─ Taxa de proposta: qualificado → proposta enviada
├─ Taxa de fechamento: proposta → fechado
├─ Tempo médio no pipeline
├─ Leads perdidos (por motivo)
└─ Sequência média de atividades até fechamento

Produtividade:
├─ Interações por dia
├─ Sequência ativa (dias com ≥1 atividade)
├─ Follow-ups vencidos (sinal de falta de atenção)
└─ Leads sem resposta há 7+ dias (candidates to churn)

Segmentação:
├─ Distribuição: odonto vs estética vs médica
├─ Taxa de conversão por segmento
└─ Pipeline médio por segmento
```

---

## 🐛 Troubleshooting

### Dashboard não carrega
- Verifique se o servidor está running: `http://localhost:8000/health`
- Check console do browser (F12) para erros JS
- Verifique logs do servidor

### Leads não aparecem na tabela
- Verifique se existem leads no banco: `GET /api/leads?page_size=100`
- Check filtros (pode estar filtrando errado)
- Verifique timezone (DEFAULT_TIMEZONE correto?)

### Daily summary não chega
- Verifique se `DISABLE_DAILY_SUMMARY` é `false`
- Verifique `DEFAULT_TIMEZONE` (deve ser IANA name tipo "America/Sao_Paulo")
- Verifique se houve atividade naquele dia (precisa ≥1 interação para enviar)
- Check logs: `daily_summary_loop iniciado | hora=...`
- Teste manualmente: `GET /api/stats` deve retornar dados

### API retorna 404
- Verifique se `lead_id` existe
- Verifique path: `/api/leads` vs `/api/leads/{id}`
- Método HTTP correto? (GET, POST, PUT, DELETE)

### Mudanças no Sheets não refletem no dashboard
- Aguarde 15 minutos (SHEETS_SYNC_INTERVAL_MINUTES) ou chame `POST /sync/sheets-to-db`
- Dashboard lê do PostgreSQL, não direto do Sheets

---

## 📚 Resumo de arquivos

| Arquivo | Linhas | Propósito |
|---------|--------|-----------|
| `app/routers/api_leads.py` | 77 | REST API endpoints (GET/POST/PUT/DELETE) |
| `app/routers/dashboard_ui.py` | 22 | HTML routes (Jinja2) |
| `app/templates/base.html` | 68 | Layout base, nav, estrutura |
| `app/templates/dashboard.html` | 55 | Stats page, cards, charts |
| `app/templates/leads.html` | 247 | Leads CRUD, filtros, modal |
| `app/static/style.css` | 920 | Mobile-first CSS |
| `app/static/dashboard.js` | 110 | Stats loading, charts |
| `app/static/leads.js` | 400 | CRUD, filtering, modal logic |
| `app/services/db_service.py` | +120 | 6 novos métodos |
| `app/config.py` | +5 | 3 novas env vars |
| `app/main.py` | +120 | Background loop, message builder |

**Total adicionado:** ~2.000 linhas de código (backend + frontend)

---

## 🎓 Aprendizados & best practices aplicadas

1. **Mobile-first design** — começou no celular, escala pro desktop
2. **Sem dependências externas** — apenas o que FastAPI + vanilla JS oferecem
3. **Timezone-aware** — sempre respeita o timezone do usuário
4. **Idempotência** — daily summary usa `last_sent_date` para não duplicar
5. **Graceful degradation** — sem atividade = sem noise (não envia summary)
6. **UX profissional** — badges, cores, confirmações claras, sem gamificação óbvia
7. **API first** — frontend consome APIs, fácil de reutilizar (mobile app futuro)
8. **Background tasks** — loops assíncronos para operações que não precisam ser síncronas

---

## 📞 Próximos passos

1. **Homologar em produção** (já está no Railway)
2. **Coletar feedback** dos vendedores nos primeiros dias
3. **Ajustar timezone se necessário** (se não for São Paulo)
4. **Monitorar performance** (DB queries, API response time)
5. **Planejar V2** (automações, bulk actions, advanced analytics)

---

**Documentação atualizada em:** 2026-03-08
**Última versão:** main branch (`claude/analyze-project-XnE4G`)
