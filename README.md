# IziDesk

**CRM comercial + Inbox WhatsApp com IA — tudo num só lugar.**

IziDesk conecta um número WhatsApp (via Evolution API) ao seu processo comercial. Ele opera em dois modos complementares:

- **Modo CRM** — você digita mensagens rápidas num grupo WhatsApp e a IA extrai, estrutura e persiste os dados dos seus leads automaticamente.
- **Modo Inbox** *(MVP 2.0)* — todas as conversas individuais recebidas no número são capturadas, transcritas, classificadas por IA e apresentadas num painel de atendimento com sugestão de resposta.

---

## Para o usuário — o que é e como usar

### O que é o IziDesk?

É uma plataforma de atendimento e CRM integrada diretamente ao seu WhatsApp. Você conecta um número e passa a ter visibilidade total de todas as conversas e leads — com IA trabalhando para você em segundo plano.

Não precisa copiar nada manualmente. A IA lê, classifica e sugere o que fazer.

> **Importante — abordagem do MVP 2.0 (Inbox):**
> O Inbox é **100% inbound**. Você não inicia contatos pelo sistema — você responde quem te chamar. A ideia é simples: o cliente chega pelo WhatsApp, a IA organiza e prioriza, você atende de forma rápida e estruturada direto do painel.
> Auto-Send e Prospecção ativa são funcionalidades do **Modo CRM** (uso interno/operacional) e não fazem parte do fluxo de atendimento Inbox.

---

### Funcionalidades principais

#### Inbox WhatsApp — atendimento inbound (MVP 2.0)

O núcleo do produto. Toda conversa recebida no número é capturada e organizada automaticamente.

- **Painel unificado** — todas as conversas recebidas em um só lugar, ordenadas por urgência.
- **Classificação automática por IA** — cada conversa é categorizada como: Suporte, Vendas, Financeiro, Informação, Spam ou Outro.
- **Prioridade automática** — Urgente, Alta, Normal ou Baixa, baseada no contexto real da conversa.
- **Resumo e sugestão de resposta** — a IA lê a conversa e gera um rascunho de resposta; você usa com um clique ou edita.
- **Transcrição de áudios** — mensagens de voz são transcritas automaticamente; você lê em vez de ouvir.
- **Resposta direta pelo painel** — você escreve ou usa a sugestão e envia; a mensagem vai para o WhatsApp do contato.
- **Gestão de status** — marque conversas como Resolvidas ou Arquivadas para manter o inbox limpo.
- **Re-análise sob demanda** — force uma nova análise da IA a qualquer momento com um clique.

#### Dashboard — visão operacional

- Contadores em tempo real: conversas abertas, urgentes, não lidas, resolvidas hoje.
- **"Atenção agora"** — lista destacada das conversas urgentes/alta prioridade para acesso imediato.
- Gráfico de volume dos últimos 7 dias.
- Distribuição por categoria (suporte vs vendas vs financeiro etc.).
- Pipeline CRM compacto.
- Auto-refresh a cada 60 segundos.

#### CRM de leads — registro interno (modo grupo)

Ferramenta para quem precisa registrar interações comerciais de forma rápida, sem formulários.

- Você escreve no grupo WhatsApp dedicado ("Falei com João, quer demo sexta") e a IA extrai e salva o lead.
- Cada lead tem: nome, empresa, cidade, segmento, telefone, status no funil e histórico.
- Funil: `novo` → `1º contato` → `qualificado` → `negociando` → `fechado`.
- Comandos rápidos no grupo: `leads hoje`, `followup`, `pipeline`.

#### Automações de background (CRM)

Estas automações rodam em segundo plano para o modo CRM — não afetam o inbox:

- **9h** — lista de follow-ups do dia enviada no grupo.
- **18h30** — resumo do dia (leads gerados, interações).
- Leads sem resposta há 5+ dias marcados como frios automaticamente.

---

### Como usar no dia a dia

**Atendimento via Inbox:**
1. Acesse `/inbox` no painel web.
2. As conversas aparecem ordenadas por prioridade — as urgentes no topo.
3. Clique numa conversa para abrir o histórico completo.
4. No painel lateral direito: leia o resumo da IA e a sugestão de resposta.
5. Clique em **"Usar sugestão"** ou escreva sua própria resposta e envie com `Ctrl+Enter`.
6. Quando finalizar o atendimento, clique em **Resolver**.

**Registro de leads via CRM (grupo):**
1. Escreva no grupo WhatsApp dedicado sobre qualquer interação ("Clínica X SP, fechou hoje").
2. A IA confirma e atualiza — você recebe confirmação em segundos.
3. Use `followup` para ver quem contatar hoje.
4. Use `pipeline` para ver o estado do funil.

---

## Sumário

1. [Como funciona — visão geral](#como-funciona--visão-geral)
2. [Modo CRM (grupo)](#modo-crm-grupo)
3. [Modo Inbox (MVP 2.0)](#modo-inbox-mvp-20)
4. [Funcionalidades completas](#funcionalidades-completas)
5. [Stack de tecnologia](#stack-de-tecnologia)
6. [Banco de dados](#banco-de-dados)
7. [API REST](#api-rest)
8. [Configuração](#configuração)
9. [Deploy](#deploy)
10. [Estrutura de arquivos](#estrutura-de-arquivos)

---

## Como funciona — visão geral

```
Número WhatsApp conectado
        │
        ▼
Evolution API  ──►  POST /webhook/evolution
                          │
              ┌───────────┴───────────┐
              │                       │
        É o grupo CRM?          É mensagem individual
              │                 + INBOX_MODE_ENABLED?
              ▼                       ▼
       Modo CRM                 Modo Inbox
   (extrai lead,            (cria conversa, transcreve,
    atualiza pipeline)       classifica, sugere resposta)
```

Os dois modos funcionam **em paralelo no mesmo processo**. O webhook identifica a origem e roteia corretamente.

---

## Modo CRM (grupo)

Você opera por um grupo WhatsApp dedicado. Tudo que você digitar lá é interpretado como uma atualização de CRM.

### Fluxo de uma mensagem

```
Você escreve no grupo:
"Clínica Sorriso SP, falei com a Dra. Ana hoje, quer demo na sexta"

    ▼ normalize_evolution_payload()
    Extrai: msg_id, chat_id, raw_text, timestamp

    ▼ Deduplicação
    msg_id já existe em atividades? → ignora

    ▼ Filtro de vagueza
    "ok", "oi", "teste" → ignora

    ▼ Detecção de intenção especial
    ┌─ "leads hoje" / "followup" / "pipeline" → Query CRM
    ├─ "followup [nome] [data]" → Agenda follow-up
    ├─ "ANALISAR: [conversa]" → Análise de conversa com IA
    ├─ "contato inicial realizado nesses N" → Bulk first contact
    ├─ "VINCULAR L0001" → Vincula atividade a lead
    └─ Padrão verbal simples ("Clínica X fechou") → Micro-update

    ▼ GPT-4o-mini extrai JSON estruturado
    intent, nome, cidade, segmento, whatsapp,
    status_sugerido, followup_em, acao_followup, resumo

    ▼ Matching de lead (PostgreSQL)
    1. Telefone exato        → score 1.00
    2. E-mail                → score 0.995
    3. Instagram normalizado → score 0.99
    4. lead_key (cidade+nome)→ score 0.98
    5. Substring             → score 0.90
    6. Fuzzy (jaro_winkler)  → score variável

    ≥ 0.88 → match automático (upsert)
    0.78–0.88 → ambíguo → pergunta no grupo
    < 0.78 → cria novo lead

    ▼ Persiste em PostgreSQL
    leads + atividades

    ▼ Sync Google Sheets
    Espelho write-only

    ▼ Confirmação no grupo
    ". CRM atualizado — Clínica Sorriso (L0042)"
```

### Comandos especiais no grupo

| Comando | O que faz |
|---------|-----------|
| `leads hoje` | Lista leads criados hoje |
| `followup` | Lista follow-ups vencidos |
| `pipeline` | Resumo do funil por status |
| `followup [nome] [data]` | Agenda próximo contato |
| `ANALISAR: [conversa]` | Análise comercial da conversa com IA |
| `VINCULAR L0001` | Vincula última atividade ao lead especificado |
| `CORRIGIR L0001 campo=valor` | Corrige campos do lead |
| `[qualificado]` | Status override entre colchetes |
| `contato inicial realizado nesses 5` | Marca os 5 leads mais recentes como "1º contato" |

### Status do funil

```
novo → 1º contato → qualificado → negociando → fechado
                ↘ sem resposta
                ↘ em espera
                ↘ perdido
                ↘ contato inválido
```

### Automações do CRM

**Auto-Send** — envia o primeiro contato automaticamente para leads `novo` com WhatsApp:
- Respeita janela horária (padrão 09h–18h, fuso SP)
- Limite diário configurável (padrão 7 envios/dia)
- 3 variantes de mensagem (A/B/C) determinísticas por lead
- Se envio falhar → marca `auto_erro`, exibe badge de aviso no lead
- Intervalo aleatório entre envios para parecer humano

**Loops de background:**
- **3h diariamente** — leads "contato feito" sem resposta há 5+ dias → temperatura `frio`
- **9h diariamente** — envia lista de follow-ups do dia para o grupo CRM
- **18h30 diariamente** — resumo do dia (leads, interações, streak) no grupo

---

## Modo Inbox (MVP 2.0)

Ativado com `INBOX_MODE_ENABLED=true`. Processa **todas** as conversas individuais recebidas no número.

### Fluxo de uma mensagem individual

```
Contato envia "oi, o vídeo não exportou" para o número

    ▼ Webhook recebe
    is_group = false → roteado para InboxService

    ▼ get_or_create_conversa(jid)
    Upsert por JID (@s.whatsapp.net) — cria thread se nova

    ▼ Transcrição (se áudio)
    OpenAI Whisper → texto

    ▼ add_mensagem_inbox()
    Persiste em mensagens_inbox
    Atualiza contadores: total_mensagens, nao_lidas, ultimo_msg_em

    ▼ asyncio.create_task(_triage_conversa)  ← não bloqueia resposta
         │
         ├─ Busca últimas 30 mensagens da thread
         ├─ Formata: "Contato: oi, o vídeo não exportou"
         ├─ GPT-4o-mini classifica:
         │     categoria  = suporte
         │     prioridade = alta
         │     resumo     = "Cliente relatou falha na exportação de vídeo"
         │     resposta_sugerida = "Olá! Entendi, vou te ajudar..."
         │     confianca  = 7
         └─ update_conversa_triage() → persiste no DB

    ▼ Webhook retorna {ok: true, conversa_id: 42}
```

**Importante:** a triagem só roda quando **o contato** envia mensagem. Quando o atendente responde, não re-classifica (evita desperdício de tokens e reclassificação incorreta após resposta enviada).

### Categorias de triagem

| Categoria | Quando |
|-----------|--------|
| `suporte` | Produto não funciona, bug, erro, acesso negado |
| `vendas` | Quer comprar, demo, orçamento, interesse em assinar |
| `financeiro` | Cobrança, cancelamento, reembolso, upgrade de plano |
| `informacao` | Como funciona, dúvida sobre feature, integração |
| `spam` | Promoção não solicitada, bot, conteúdo irrelevante |
| `outro` | Não se encaixa claramente nas anteriores |

### Prioridades

| Prioridade | Critério |
|------------|----------|
| `urgente` | Produto fora do ar para cliente pagante, chargeback, bug crítico em produção |
| `alta` | Lead quente pronto para fechar, trial expirando, cliente sem resposta há 2h+ |
| `normal` | Conversa em andamento sem urgência |
| `baixa` | Spam, conversa muito antiga, sem intenção clara |

### Painel de Inbox (`/inbox`)

- Lista todas as conversas com filtros: status (aberto/resolvido/arquivado), categoria, prioridade, busca por nome/número
- Cards ordenados por prioridade → recência
- Badge de não-lidas (zerado ao abrir a conversa)
- Indicador visual de prioridade (borda lateral colorida)

### Detalhe de conversa (`/inbox/{id}`)

- Thread completo de mensagens (estilo WhatsApp Web)
- Áudios exibidos com transcrição inline
- Painel lateral: resumo da IA, confiança (1–10), categoria/prioridade editáveis, lead CRM vinculado
- Sugestão de resposta com botão "Usar sugestão"
- Caixa de resposta: envio via WhatsApp com `Ctrl+Enter`
- Botões: Resolver, Arquivar, Reabrir
- Re-análise sob demanda (força nova triagem da IA)
- Auto-refresh a cada 15s para capturar novas mensagens

---

## Funcionalidades completas

### Dashboard (`/dashboard`)

- **Hero stats**: conversas abertas, urgentes, não lidas, resolvidas hoje
- **Atenção agora**: lista das conversas urgentes/alta prioridade com acesso direto
- **Gráfico de categorias**: volume por suporte/vendas/financeiro/informação/spam
- **Volume 7 dias**: conversas criadas por dia na última semana
- **Pipeline CRM**: funil de leads por status (compacto)
- **Aguardando resposta**: conversas normais com não-lidas
- **CRM resumo**: leads ativos, follow-ups hoje, novos na semana
- Auto-refresh a cada 60s

### Leads (`/leads`)

- Listagem com filtros: status, temperatura, segmento, busca textual
- Cards e visualização em tabela
- Histórico completo de atividades por lead
- Perfil de comunicação (melhor horário, canal preferido)
- CRUD completo (criar, editar, excluir)
- Importação em massa (bulk upsert via JSON)
- Badge `⚠️ Nº inválido` para leads com falha no auto-send *(funcionalidade do Modo CRM)*
- Botão "Reativar fila" para desbloquear leads com `auto_erro`

### Prospecção (`/prospeccao`)

- Busca de leads por tipo de negócio + cidade em 3 fontes:
  - **OpenStreetMap** — dados públicos geográficos
  - **Telelistas** — diretório de empresas brasileiras
  - **Apontador** — guia comercial
- Enriquecimento assíncrono de WhatsApp (scraping)
- Fila de revisão: pendente / aprovado / descartado
- Aprovação individual ou em lote (só os com WhatsApp)
- Ao aprovar: cria lead no CRM automaticamente

### Estatísticas (`/estatisticas`)

- Análises de conversas: distribuição de confiança, últimas análises
- KPIs gerais: total de leads, taxa de fechamento, segmentos
- A/B testing de mensagens: taxa de resposta por variante

---

## Stack de tecnologia

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.11 · FastAPI 0.115 · Uvicorn |
| Banco de dados | PostgreSQL 12+ (psycopg2, connection pool) |
| Templates | Jinja2 · HTML/CSS/JS vanilla (sem framework) |
| IA — extração | OpenAI GPT-4o-mini |
| IA — transcrição | OpenAI Whisper-1 |
| IA — triagem inbox | OpenAI GPT-4o-mini |
| WhatsApp | Evolution API (webhook + send) |
| Sync legado | Google Sheets API via gspread |
| Scraping | BeautifulSoup · httpx · DuckDuckGo |
| Matching | RapidFuzz (jaro_winkler) |
| Deploy | Docker · Railway |

---

## Banco de dados

### Tabela `leads`

Registro principal de cada prospect/cliente.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `lead_id` | TEXT PK | ID sequencial (L0001, L0002…) |
| `nome` | TEXT | Nome da empresa/pessoa |
| `cidade` | TEXT | Cidade |
| `segmento` | TEXT | odontologia / medicina / estetica / psicologia / outros |
| `whatsapp` | TEXT | Número normalizado (+5511…) |
| `email` | TEXT | E-mail |
| `instagram` | TEXT | Handle do Instagram |
| `site` | TEXT | URL do site |
| `responsavel` | TEXT | Nome/cargo do contato |
| `fonte` | TEXT | Canal de origem (cold, indicação, instagram…) |
| `status` | TEXT | Estágio no funil |
| `temperatura` | TEXT | frio / morno / engajado / quente / cliente |
| `resumo` | TEXT | Resumo executivo gerado pela IA |
| `acao_followup` | TEXT | Próxima ação concreta |
| `proximo_followup_em` | TEXT | Data do próximo contato (ISO) |
| `mensagem_enviada_em` | TEXT | Quando o auto-send enviou |
| `origem_primeiro_contato` | TEXT | `''` / `manual` / `automatico` / `auto_erro` |
| `auto_send_variante` | TEXT | A / B / C |

### Tabela `atividades`

Log de todas as interações processadas pelo webhook.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | — |
| `msg_id` | TEXT UNIQUE | ID de deduplicação (do Evolution API) |
| `lead_id` | TEXT | Lead associado |
| `tipo` | TEXT | contato inicial / respondeu / pediu proposta… |
| `canal` | TEXT | whatsapp_group / whatsapp |
| `acao_executada` | TEXT | criar_lead / atualizar_lead / registrar_atividade… |
| `confianca_ia` | REAL | Score 0–1 da interpretação |
| `confianca_analise` | INT | Score 1–10 (só para tipo "análise de conversa") |
| `duracao_audio_s` | REAL | Duração do áudio transcrito |
| `mensagem_bruta` | TEXT | Texto original |
| `resumo` | TEXT | Resumo gerado pela IA |
| `followup_em` | TEXT | Data de follow-up extraída |

### Tabela `lead_prospects`

Fila de prospecção aguardando revisão.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | — |
| `nome` | TEXT | Nome da empresa |
| `cidade` | TEXT | Cidade |
| `segmento` | TEXT | Segmento |
| `telefone` | TEXT | Telefone bruto |
| `whatsapp` | TEXT | WhatsApp enriquecido (se encontrado) |
| `website` | TEXT | URL do site |
| `instagram` | TEXT | Perfil Instagram |
| `link_maps` | TEXT | Google Maps |
| `rating` | TEXT | Avaliação (se disponível) |
| `fonte` | TEXT | osm / telelistas / apontador |
| `status_revisao` | TEXT | pendente / aprovado / descartado |
| `enriquecido` | INT | 0 = pendente, 1 = concluído |
| `busca_id` | TEXT | ID da busca que gerou o prospect |
| `lead_id_aprovado` | TEXT | ID do lead CRM após aprovação |

### Tabela `conversas` *(MVP 2.0)*

Thread de cada contato no inbox.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | — |
| `jid` | TEXT UNIQUE | JID do WhatsApp (número@s.whatsapp.net) |
| `nome_contato` | TEXT | Nome detectado |
| `numero` | TEXT | Número sem sufixo |
| `status` | TEXT | aberto / resolvido / arquivado |
| `prioridade` | TEXT | urgente / alta / normal / baixa |
| `categoria` | TEXT | suporte / vendas / financeiro / informacao / spam / outro |
| `total_mensagens` | INT | Total de mensagens na thread |
| `nao_lidas` | INT | Não lidas (zerado ao abrir) |
| `ultimo_msg_em` | TIMESTAMPTZ | Última mensagem recebida |
| `primeira_msg_em` | TIMESTAMPTZ | Primeira mensagem recebida |
| `resumo_ia` | TEXT | Resumo factual gerado pela IA |
| `resposta_sugerida` | TEXT | Rascunho de resposta da IA |
| `confianca_ia` | INT | Score 1–10 da triagem |
| `lead_id` | TEXT | Lead CRM vinculado (opcional) |
| `atribuido_a` | TEXT | Atendente responsável |
| `resolvido_em` | TIMESTAMPTZ | Quando foi resolvida |

### Tabela `mensagens_inbox` *(MVP 2.0)*

Mensagens individuais de cada thread.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | — |
| `msg_id` | TEXT UNIQUE | ID de deduplicação |
| `conversa_id` | INT FK | Referência para `conversas.id` |
| `jid` | TEXT | JID do remetente |
| `de_mim` | BOOLEAN | `true` = enviada pelo atendente |
| `tipo` | TEXT | text / audio / image / document / video |
| `texto` | TEXT | Conteúdo textual |
| `transcricao` | TEXT | Transcrição de áudio (Whisper) |
| `duracao_audio_s` | REAL | Duração em segundos |
| `media_url` | TEXT | URL da mídia |
| `status_proc` | TEXT | pendente / processado / erro |
| `enviado_em` | TIMESTAMPTZ | Timestamp original da mensagem |

### Tabela `msg_ab_eventos`

Rastreamento de A/B testing nas mensagens de primeiro contato.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `lead_id` | TEXT | — |
| `variante` | TEXT | A / B / C |
| `segmento` | TEXT | Segmento do lead |
| `evento` | TEXT | copiada / respondeu / auto_enviada |
| `tipo` | TEXT | inicial / fu1 / fu2 |

### Tabela `settings_kv`

Configurações persistidas no banco (sobrescrevem `.env`).

| Chave | Valor padrão | Descrição |
|-------|-------------|-----------|
| `auto_send_enabled` | `false` | Liga/desliga auto-send |

---

## API REST

### Inbox (MVP 2.0)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/inbox/dashboard` | Todos os dados do dashboard em uma chamada |
| `GET` | `/api/inbox/stats` | Contadores: abertas, urgentes, não lidas, por categoria |
| `GET` | `/api/inbox/conversas` | Lista com filtros (`status`, `categoria`, `prioridade`, `search`, `page`) |
| `GET` | `/api/inbox/conversas/{id}` | Conversa + mensagens; zera contador de não lidas |
| `PUT` | `/api/inbox/conversas/{id}` | Atualiza campos (status, prioridade, categoria, lead_id…) |
| `POST` | `/api/inbox/conversas/{id}/resolver` | Marca como resolvida |
| `POST` | `/api/inbox/conversas/{id}/arquivar` | Arquiva |
| `POST` | `/api/inbox/conversas/{id}/reabrir` | Reabre |
| `POST` | `/api/inbox/conversas/{id}/analisar` | Força nova triagem com IA |
| `POST` | `/api/inbox/conversas/{id}/responder` | Envia resposta via WhatsApp `{text: "..."}` |

### Leads (CRM)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/stats` | KPIs do dashboard CRM |
| `GET` | `/api/leads` | Lista com filtros e paginação |
| `GET` | `/api/leads/{id}` | Detalhes do lead |
| `GET` | `/api/leads/{id}/atividades` | Histórico de atividades |
| `GET` | `/api/leads/{id}/perfil` | Perfil de comunicação |
| `POST` | `/api/leads` | Cria lead |
| `PUT` | `/api/leads/{id}` | Atualiza lead |
| `DELETE` | `/api/leads/{id}` | Remove lead |
| `POST` | `/api/leads/bulk` | Importação em massa (upsert) |
| `POST` | `/api/leads/reativar-auto-erro` | Desbloqueia leads com falha no auto-send |

### Auto-Send

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/auto-send/status` | Status, fila e contador diário |
| `POST` | `/api/auto-send/toggle` | Liga/desliga |
| `GET` | `/api/auto-send/historico` | Histórico de envios |

### Prospecção

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/prospeccao/buscar` | Inicia busca `{segmento, cidade, limit, fontes}` |
| `GET` | `/api/prospeccao/fila` | Lista a fila de revisão |
| `GET` | `/api/prospeccao/contadores` | Contagem por status de revisão |
| `GET` | `/api/prospeccao/status/{busca_id}` | Status do enriquecimento |
| `PUT` | `/api/prospeccao/{id}/aprovar` | Aprova e cria lead CRM |
| `PUT` | `/api/prospeccao/{id}/descartar` | Descarta |
| `POST` | `/api/prospeccao/aprovar-lote` | Aprova todos com WhatsApp |
| `DELETE` | `/api/prospeccao/fila/descartados` | Limpa descartados |

### Outros

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/webhook/evolution` | Entrada principal do WhatsApp |
| `GET` | `/health` | Health check |
| `POST` | `/sync/sheets-to-db` | Sincroniza Sheets → DB manualmente |

---

## Configuração

Todas as variáveis de ambiente (copie `.env.example` para `.env`):

### Obrigatórias

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@host/db`) |
| `OPENAI_API_KEY` | Chave da OpenAI (GPT-4o-mini + Whisper) |
| `EVOLUTION_API_URL` | URL base da Evolution API (ex: `https://evo.seudominio.com`) |
| `EVOLUTION_API_KEY` | API key da instância Evolution |
| `EVOLUTION_INSTANCE_NAME` | Nome da instância no Evolution |

### CRM

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CRM_TARGET_GROUP_ID` | — | ID do grupo WhatsApp CRM (formato `120363...@g.us`) |
| `EVOLUTION_WEBHOOK_SECRET` | — | Secret para validar webhooks |
| `DISABLE_EVOLUTION_CONFIRMATION` | `false` | Desativa confirmações no grupo |
| `DISABLE_DAILY_SUMMARY` | `false` | Desativa resumo diário |
| `DAILY_SUMMARY_HOUR` | `18` | Hora do resumo diário |
| `DAILY_SUMMARY_MINUTE` | `30` | Minuto do resumo diário |

### Inbox MVP 2.0

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `INBOX_MODE_ENABLED` | `false` | **Liga o modo inbox** para conversas individuais |

### Auto-Send

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AUTO_SEND_ENABLED` | `false` | Liga o auto-send (pode ser alterado pelo dashboard) |
| `AUTO_SEND_DIARIO_MAX` | `7` | Máximo de envios por dia |
| `AUTO_SEND_HORA_INICIO` | `9` | Início da janela de envio (hora) |
| `AUTO_SEND_HORA_FIM` | `18` | Fim da janela de envio (hora) |
| `AUTO_SEND_INTERVALO_MIN_S` | `180` | Intervalo mínimo entre envios (segundos) |
| `AUTO_SEND_INTERVALO_MAX_S` | `720` | Intervalo máximo entre envios (segundos) |

### Google Sheets (legado / opcional)

| Variável | Descrição |
|----------|-----------|
| `GOOGLE_SHEETS_ID` | ID da planilha |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON da service account (ou caminho para o arquivo) |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Alternativa: JSON em base64 |

### Outros

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DEFAULT_TIMEZONE` | `America/Sao_Paulo` | Fuso horário para todos os cálculos de data/hora |

---

## Deploy

### Railway (recomendado)

1. Fork/clone o repositório
2. Crie um novo serviço no Railway apontando para o branch desejado
3. Adicione um banco PostgreSQL no Railway (provisioned automaticamente)
4. Configure as variáveis de ambiente listadas acima
5. O `Dockerfile` cuida do resto

**Para MVP 2.0 (Inbox):**
- Use o branch `claude/mvp-2-iziprospect-saas`
- Adicione `INBOX_MODE_ENABLED=true`
- No painel da Evolution API, configure o webhook para enviar **todos os tipos de mensagem** (não só grupos), evento `MESSAGES_UPSERT`

### Docker local

```bash
cp .env.example .env
# edite .env com suas credenciais
docker build -t iziprospect .
docker run -p 8000:8000 --env-file .env iziprospect
```

### Webhook da Evolution API

Configure no painel da Evolution:
```
URL: https://SEU-DOMINIO/webhook/evolution
Headers: X-Webhook-Secret: SEU_SECRET
Eventos: MESSAGES_UPSERT
```

As tabelas do banco são criadas automaticamente no startup da aplicação.

---

## Estrutura de arquivos

```
iziprospect/
├── app/
│   ├── main.py                    # FastAPI app, webhook principal, loops de background
│   ├── config.py                  # Configurações via variáveis de ambiente
│   ├── schemas/
│   │   └── models.py              # Pydantic models (NormalizedEvent, LLMExtraction…)
│   ├── routers/
│   │   ├── api_leads.py           # CRUD de leads, stats, auto-send
│   │   ├── api_inbox.py           # Inbox MVP 2.0: conversas, triagem, resposta
│   │   ├── api_prospeccao.py      # Prospecção e fila de revisão
│   │   └── dashboard_ui.py        # Rotas HTML (páginas)
│   ├── services/
│   │   ├── db_service.py          # Toda a camada de banco de dados (PostgreSQL)
│   │   ├── inbox_service.py       # Lógica do inbox: processar, transcrever, triar
│   │   ├── auto_sender.py         # Envio automático de primeiro contato
│   │   ├── crm_interpreter.py     # Detecção de intenções CRM nas mensagens
│   │   ├── evolution_service.py   # Cliente da Evolution API (enviar, buscar áudio)
│   │   ├── openai_service.py      # GPT-4o-mini (extração, análise) + Whisper
│   │   ├── normalizer.py          # Normaliza payload do webhook → NormalizedEvent
│   │   ├── prospector_service.py  # Scraping e enriquecimento de prospects
│   │   └── sheets_service.py      # Sync com Google Sheets
│   ├── templates/
│   │   ├── base.html              # Layout base com sidebar e navegação
│   │   ├── dashboard.html         # Dashboard inbox-first
│   │   ├── inbox.html             # Lista de conversas do inbox
│   │   ├── conversa.html          # Detalhe de uma conversa
│   │   ├── leads.html             # Gestão de leads CRM
│   │   ├── prospeccao.html        # Fila de prospecção
│   │   ├── estatisticas.html      # Analytics
│   │   └── landing.html           # Landing page
│   └── static/
│       ├── style.css              # Estilos (mobile-first, dark mode)
│       ├── dashboard.js           # Dashboard
│       ├── inbox.js               # Página inbox
│       ├── conversa.js            # Página de conversa
│       ├── leads.js               # Página de leads
│       ├── prospeccao.js          # Página de prospecção
│       └── estatisticas.js        # Página de estatísticas
├── tests/
│   ├── test_config.py
│   ├── test_crm_interpreter.py
│   └── test_utils.py
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md                      # Este arquivo
└── CHANGELOG.md                   # Histórico de mudanças por versão
```

---

## Branches

| Branch | Descrição |
|--------|-----------|
| `claude/analyze-project-XnE4G` | Produção atual — Modo CRM estável |
| `claude/mvp-2-iziprospect-saas` | MVP 2.0 — Inbox WhatsApp completo |

---

*Construído com FastAPI, PostgreSQL, OpenAI e Evolution API.*
