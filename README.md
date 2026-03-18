# IziProspect — CRM Comercial com WhatsApp

CRM invisível para operação comercial: captura leads via mensagens no WhatsApp (texto e áudio), processa com IA, organiza em banco de dados PostgreSQL e sincroniza com Google Sheets. Inclui dashboard web, gestão de leads, prospecção automática e envio automático de primeiro contato.

---

## Funcionalidades

- **Webhook WhatsApp**: recebe mensagens via Evolution API (texto e áudio)
- **Transcrição de áudio**: via Whisper (OpenAI)
- **Extração com LLM**: GPT-4o-mini extrai estrutura (nome, cidade, segmento, telefone, etc.)
- **Matching anti-duplicação**: fuzzy matching com RapidFuzz para não criar leads duplicados
- **Dashboard web**: KPIs, funil, leads por segmento e cidade
- **Gestão de leads**: CRUD completo, histórico, busca e importação em massa
- **Prospecção automática**: busca em OpenStreetMap, Telelistas e Apontador com enriquecimento de WhatsApp
- **Auto-Send**: envio automático de primeiro contato com variantes A/B/C por segmento
- **Analytics**: distribuição de confiança da IA, análise de conversas, rastreamento de A/B
- **Sync Google Sheets**: espelho de leads e atividades em tempo real

---

## Arquitetura

```
WhatsApp Group (Evolution API)
    │
    ▼
POST /webhook/evolution
    │
    ├─ Normaliza payload → msg_id, msg_type, raw_text, media_url, timestamp, chat_id
    ├─ Idempotência: msg_id já existe em atividades? → retorna {duplicate: true}
    ├─ Filtra mensagens vagas ("ok", "oi", "teste") antes de chamar OpenAI
    │
    ├─ [áudio] → Baixa + descriptografa .enc → Transcreve com Whisper
    │
    ├─ GPT-4o-mini extrai JSON estruturado:
    │     intent, nome, cidade, segmento, whatsapp, status, followup_em, resumo
    │
    ├─ Matching de lead:
    │     whatsapp → instagram → lead_key → contains → fuzzy
    │     ≥0.88: match automático
    │     0.78–0.88: envia para REVISAR (ambíguo)
    │     <0.78: cria novo lead
    │
    ├─ Upsert em PostgreSQL (leads + atividades)
    ├─ Sync para Google Sheets
    └─ Envia confirmação de volta ao grupo
```

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI 0.115 + Uvicorn |
| Banco de dados | PostgreSQL 12+ |
| Templates | Jinja2 + HTML/CSS/JS vanilla |
| IA / Transcrição | OpenAI API (GPT-4o-mini + Whisper) |
| WhatsApp | Evolution API (webhook) |
| Sync | Google Sheets API via gspread |
| Scraping / Enriquecimento | BeautifulSoup, httpx, DuckDuckGo |
| Matching | RapidFuzz (jaro_winkler) |
| Deploy | Docker + Railway |

---

## Pré-requisitos

- Python 3.11+
- PostgreSQL 12+
- Conta OpenAI com acesso a Whisper e Chat Completions
- Google Cloud: Sheets API habilitada + Service Account com permissão de Editor na planilha
- Evolution API configurada com webhook apontando para este serviço

---

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

```bash
# — Obrigatórias —
OPENAI_API_KEY=                          # Chave OpenAI
DATABASE_URL=postgresql://user:pass@host:5432/dbname  # PostgreSQL
GOOGLE_SHEETS_ID=                        # ID da planilha Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON='{...}'      # JSON da service account (ou use a variável _BASE64 abaixo)
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=      # JSON encodado em base64 (preferível no Railway)

# — WhatsApp / Evolution API —
EVOLUTION_API_URL=                       # URL base da Evolution API
EVOLUTION_API_KEY=                       # Chave da Evolution API
EVOLUTION_INSTANCE_NAME=                 # Nome da instância WhatsApp
EVOLUTION_WEBHOOK_SECRET=                # Secret HMAC para validar webhooks (opcional)
CRM_TARGET_GROUP_ID=                     # JID do grupo autorizado (ex: 5511999999999@g.us)
DISABLE_EVOLUTION_CONFIRMATION=false     # true = não envia confirmação de volta ao grupo

# — Comportamento —
DEFAULT_TIMEZONE=America/Sao_Paulo       # Fuso horário para agendamentos
SHEETS_SYNC_INTERVAL_MINUTES=15          # Frequência de sync com Sheets
DAILY_SUMMARY_HOUR=18                    # Hora do resumo diário (formato 24h)
DAILY_SUMMARY_MINUTE=30
DISABLE_DAILY_SUMMARY=false

# — Auto-Send (desligado por padrão) —
AUTO_SEND_ENABLED=false
AUTO_SEND_DIARIO_MAX=7                   # Máximo de envios por dia
AUTO_SEND_HORA_INICIO=9                  # Janela de envio: início (24h)
AUTO_SEND_HORA_FIM=18                    # Janela de envio: fim
AUTO_SEND_INTERVALO_MIN_S=1080           # Intervalo mínimo entre envios (18 min)
AUTO_SEND_INTERVALO_MAX_S=1500           # Intervalo máximo entre envios (25 min)
```

> **Dica Railway:** prefira `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` para evitar problemas de escaping em JSON.

---

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edite com suas credenciais

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## Docker

```bash
docker build -t iziprospect .
docker run --rm -p 8000:8000 --env-file .env iziprospect
```

---

## Deploy no Railway

1. Suba o repositório no GitHub.
2. Crie novo projeto no Railway → Deploy from GitHub.
3. Configure as variáveis de ambiente (seção acima).
4. Railway detecta o `Dockerfile` e faz build automático.
5. Configure o webhook no Evolution apontando para:
   ```
   https://SEU_APP.railway.app/webhook/evolution
   ```
6. (Opcional) Defina `EVOLUTION_WEBHOOK_SECRET` e configure o mesmo valor no Evolution para validação HMAC.

---

## Configuração do Google Sheets

1. Crie uma planilha no Google Sheets.
2. Copie o ID da planilha para `GOOGLE_SHEETS_ID`.
3. No Google Cloud, habilite a **Google Sheets API**.
4. Crie uma **Service Account** e gere a chave JSON.
5. Compartilhe a planilha com o e-mail da service account como **Editor**.
6. Use o JSON em `GOOGLE_SERVICE_ACCOUNT_JSON` ou encode em base64 e use `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

> O app cria automaticamente as abas `LEADS`, `ATIVIDADES`, `REVISAR` e `MSG_AB_EVENTOS` com os headers corretos na primeira execução.

---

## Páginas do sistema

| Rota | Página | Descrição |
|---|---|---|
| `/dashboard` | Dashboard | KPIs, funil de vendas, leads por segmento e cidade |
| `/leads` | Gestão de Leads | Lista, busca, filtros, CRUD, importação em massa, histórico |
| `/estatisticas` | Analytics | Confiança da IA, análise de conversas, gráficos A/B |
| `/prospeccao` | Prospecção | Busca automática de leads, fila de aprovação |

---

## API — Endpoints principais

### Webhook
| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/webhook/evolution` | Entrada principal de mensagens WhatsApp |
| `POST` | `/sync/sheets-to-db` | Sync manual Sheets → PostgreSQL |

### Leads
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/leads` | Lista com filtros (status, segmento, temperatura, busca, paginação) |
| `GET` | `/api/leads/{id}` | Detalhes de um lead |
| `GET` | `/api/leads/{id}/atividades` | Histórico de atividades do lead |
| `GET` | `/api/leads/{id}/perfil` | Perfil de comunicação (breakdown por tipo) |
| `POST` | `/api/leads` | Criar lead |
| `PUT` | `/api/leads/{id}` | Atualizar lead |
| `DELETE` | `/api/leads/{id}` | Remover lead |
| `POST` | `/api/leads/bulk` | Importação em massa com deduplicação |
| `POST` | `/api/leads/reativar-auto-erro` | Desbloqueia leads presos no auto-send |

### Estatísticas
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/stats` | Contagens por status, temperatura e segmento |
| `GET` | `/api/estatisticas` | KPIs e funil completo |
| `GET` | `/api/analises/stats` | Distribuição de confiança da IA |

### Auto-Send
| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/auto-send/toggle` | Liga/desliga envio automático |
| `GET` | `/api/auto-send/status` | Status atual + fila + envios hoje |
| `GET` | `/api/auto-send/historico` | Histórico dos últimos 50 envios |

### Prospecção
| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/prospeccao/buscar` | Inicia busca de leads (OSM + Telelistas + Apontador) |
| `GET` | `/api/prospeccao/fila` | Lista fila de prospects com status e enriquecimento |
| `GET` | `/api/prospeccao/contadores` | Contagens por status de revisão |
| `GET` | `/api/prospeccao/status/{busca_id}` | Progresso de enriquecimento (polling) |
| `PUT` | `/api/prospeccao/{id}/aprovar` | Aprova prospect → converte em lead |
| `PUT` | `/api/prospeccao/{id}/descartar` | Descarta prospect |
| `POST` | `/api/prospeccao/aprovar-lote` | Aprova em massa (apenas com WhatsApp) |
| `DELETE` | `/api/prospeccao/fila/descartados` | Limpa descartados |

---

## Banco de dados

### Tabela `leads`

| Campo | Tipo | Descrição |
|---|---|---|
| `lead_id` | TEXT PK | Identificador único (ex: `L0042`) |
| `nome` | TEXT | Nome da clínica/empresa |
| `cidade` | TEXT | Cidade |
| `segmento` | TEXT | Segmento (odontologia, medicina, estetica…) |
| `whatsapp` | TEXT | Número WhatsApp normalizado (`+55DDD…`) |
| `instagram` | TEXT | Handle Instagram |
| `email` | TEXT | E-mail |
| `site` | TEXT | URL do site |
| `status` | TEXT | novo / contato feito / proposta enviada / conversão / perdido / fechado |
| `temperatura` | TEXT | frio / morno / quente |
| `resumo` | TEXT | Resumo gerado pela IA |
| `acao_followup` | TEXT | Ação de follow-up pendente |
| `observacoes` | TEXT | Notas manuais |
| `origem_primeiro_contato` | TEXT | automatico / manual / auto_erro / '' |
| `mensagem_enviada_em` | TEXT | Timestamp do auto-send (ISO) |
| `proximo_followup_em` | TEXT | Data/hora do próximo follow-up |

### Tabela `atividades`

| Campo | Descrição |
|---|---|
| `data_hora` | Timestamp do evento |
| `msg_id` | ID único da mensagem (idempotência) |
| `lead_id` | FK para leads |
| `tipo` | Tipo (auto_envio, mensagem, followup…) |
| `canal` | Canal (whatsapp_direto, grupo…) |
| `mensagem_bruta` | Texto original ou transcrição |
| `resumo` | Resumo gerado pela IA |

### Tabela `lead_prospects`

Fila de prospecção com nome, cidade, segmento, telefone, whatsapp, website, instagram, link_maps, fonte, status_revisao, rating e enriquecimento.

---

## Matching de leads

Prioridade:

1. `whatsapp` — match exato por telefone normalizado
2. `instagram` — match exato
3. `lead_key` — `cidade_normalizada:nome_canonico`
4. `contains` — substring no nome (mesma cidade)
5. Fuzzy (`jaro_winkler`):
   - `≥ 0.88` → match automático
   - `0.78 – 0.88` → envia para `REVISAR` com top 3 candidatos
   - `< 0.78` → cria novo lead

A normalização remove acentos, pontuação e termos genéricos (clínica, consultório, odonto, estética) para melhorar a proximidade de nomes.

---

## Auto-Send — Envio automático de primeiro contato

O sistema envia automaticamente a primeira mensagem de prospecção para leads com `status = 'novo'`. **Desligado por padrão.**

### Fluxo

```
Lead status='novo' + whatsapp preenchido
    │
    ▼ (loop a cada ~1 min)
Dentro da janela horária? → não: aguarda
    │ sim
Limite diário atingido? → sim: aguarda amanhã
    │ não
Seleciona 1 lead (FIFO, prioridade: segmento preenchido)
    │
Gera mensagem variante A/B/C (determinístico por lead_id)
    │
Envia via Evolution API
    │
Sucesso → status='contato feito', registra em atividades + msg_ab_eventos
Falha   → marca como 'auto_erro', tenta próximo lead no ciclo seguinte
```

### Variantes de mensagem

| Variante | Estratégia |
|---|---|
| A | Apresentação casual ("Oi, sou o Pedro…") |
| B | Dor-primeiro (abre com a dor do cliente) |
| C | Prova social (menciona clínicas da região) |

Templates personalizados por segmento: `odontologia`, `medicina`, `estetica`, `default`.

### Reativar leads bloqueados

Leads marcados como `auto_erro` (falha antes de algum fix) podem ser reativados na página de **Leads** com o botão **"🔄 Reativar fila"**, ou via API:

```bash
POST /api/leads/reativar-auto-erro
```

Isso reseta `origem_primeiro_contato = ''` para todos os leads `novo` com `whatsapp` preenchido que estavam bloqueados, colocando-os de volta na fila de envio.

---

## Prospecção automática

A tela de **Prospecção** busca leads automaticamente em:

1. **OpenStreetMap (Overpass API)** — dados estruturados de POIs
2. **Telelistas.net** — lista telefônica brasileira
3. **Apontador.com.br** — diretório de empresas

Após a coleta, o sistema enriquece cada prospect buscando WhatsApp via:
- Scraping do site (links `wa.me`, `api.whatsapp.com`)
- Fallback via DuckDuckGo Search

Prospects aprovados são convertidos em leads. Prospects com erro ou sem resultado podem ser descartados.

---

## Regras de robustez

- Mensagens vagas são ignoradas antes de chamar OpenAI (`message_too_vague`)
- Falha da OpenAI não quebra o webhook: retorna HTTP 200 com `{deferred: true}`
- Falha de confirmação via Evolution não quebra o processamento
- Áudio inválido ou falha de transcrição é roteado para `REVISAR`
- Duplicatas detectadas por `msg_id` (idempotência)
- Auto-send: falha de envio não altera o lead — retenta no próximo ciclo

---

## Testando localmente

### Mensagem de texto

```bash
curl -X POST http://localhost:8000/webhook/evolution \
  -H 'Content-Type: application/json' \
  -d '{
    "data": {
      "key": {"id": "ABCD1234", "remoteJid": "5511999999999@g.us"},
      "messageTimestamp": 1730803200,
      "chatId": "SEU_GROUP_ID@g.us",
      "message": {"conversation": "Novo lead: Clínica Sorriso em Campinas, 19 99898-9888"}
    }
  }'
```

### Mensagem de áudio

```bash
curl -X POST http://localhost:8000/webhook/evolution \
  -H 'Content-Type: application/json' \
  -d '{
    "data": {
      "key": {"id": "EFGH5678", "remoteJid": "5511999999999@g.us"},
      "messageTimestamp": 1730803200,
      "chatId": "SEU_GROUP_ID@g.us",
      "message": {"audioMessage": {"url": "https://cdn-evolution/audio.ogg"}}
    }
  }'
```

### Logs úteis do auto-send

```
auto_sender | enviando para lead_id=L042 nome='Clínica Sorriso' variante=B
auto_sender | OK | lead_id=L042 variante=B (3/7 hoje)
auto_sender_loop | aguardando 347s antes do próximo envio
auto_sender | limite diário atingido (7/7), aguardando amanhã
```

---

## Estrutura do projeto

```
app/
├── main.py                   # FastAPI app principal, webhook, health, sync
├── config.py                 # Configurações e parsing de env vars
├── routers/
│   ├── api_leads.py          # REST API de leads e auto-send
│   ├── api_prospeccao.py     # API de prospecção
│   └── dashboard_ui.py       # Rotas HTML
├── services/
│   ├── db_service.py         # Operações PostgreSQL (leads, atividades, prospects)
│   ├── openai_service.py     # Whisper + GPT extração estruturada
│   ├── sheets_service.py     # Sync Google Sheets
│   ├── prospector_service.py # Busca multi-fonte + enriquecimento
│   ├── auto_sender.py        # Loop de envio automático
│   ├── crm_interpreter.py    # NLU, detecção de intent, follow-up
│   ├── evolution_service.py  # Integração Evolution API
│   └── normalizer.py         # Normalização de payloads
├── schemas/
│   └── models.py             # Modelos Pydantic
├── templates/                # HTML (Jinja2): dashboard, leads, estatisticas, prospeccao
└── static/                   # CSS + JS (vanilla)
```
