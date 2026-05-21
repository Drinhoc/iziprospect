# Changelog — IziProspect

## [MVP 2.0] — Inbox WhatsApp (branch: claude/mvp-2-iziprospect-saas)

### Visão geral

MVP 2.0 transforma o IziProspect de um CRM acionado por grupo WhatsApp para uma
**plataforma de inbox completa**: qualquer conversa individual recebida no número
conectado é capturada, triada por IA e exibida num painel dedicado com sugestão
de resposta e histórico completo.

**Filosofia do MVP 2.0 — inbound puro:**
O Inbox é um canal de atendimento reativo. O sistema não envia mensagens por
iniciativa própria — ele organiza e prioriza as conversas de quem já chegou até
você. Quem manda mensagem primeiro é sempre o cliente. O atendente responde.
Auto-Send e Prospecção ativa são ferramentas do Modo CRM e não fazem parte
deste fluxo.

Inspiração: atendentes sobrecarregados com centenas de mensagens de áudio sem
nenhuma ferramenta de triagem ou priorização. O Inbox MVP 2.0 resolve exatamente
esse problema.

---

### Novos arquivos

| Arquivo | Descrição |
|---------|-----------|
| `app/services/inbox_service.py` | Serviço principal do inbox: processa mensagens, transcreve áudios e executa triagem com IA |
| `app/routers/api_inbox.py` | Router FastAPI com todos os endpoints REST do inbox |
| `app/templates/inbox.html` | Página de listagem de conversas com filtros e stats |
| `app/templates/conversa.html` | Página de detalhe: thread completo, painel IA, envio de resposta |
| `app/static/inbox.js` | JavaScript da página de inbox |
| `app/static/conversa.js` | JavaScript da página de conversa |
| `CHANGELOG.md` | Este arquivo |

---

### Arquivos modificados

| Arquivo | O que mudou |
|---------|-------------|
| `app/services/db_service.py` | +SQL para tabelas `conversas` e `mensagens_inbox` + 10 novos métodos |
| `app/config.py` | Novo campo `inbox_mode_enabled` (env: `INBOX_MODE_ENABLED`) |
| `app/main.py` | Startup migration para criar tabelas; webhook roteia não-grupos para InboxService |
| `app/routers/dashboard_ui.py` | Rotas `/inbox` e `/inbox/{id}` |
| `app/templates/base.html` | Link "Inbox" na sidebar e bottom nav; badge de não-lidas atualizado a cada 30s |
| `app/static/style.css` | ~300 linhas de CSS para inbox e conversa |

---

### Banco de dados — novas tabelas

#### `conversas`
Thread de cada contato. Um registro por JID (`número@s.whatsapp.net`).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Chave primária |
| `jid` | TEXT UNIQUE | JID do WhatsApp |
| `nome_contato` | TEXT | Nome detectado pelo Evolution API ou pela IA |
| `numero` | TEXT | Número sem sufixo `@s.whatsapp.net` |
| `status` | TEXT | `aberto` \| `resolvido` \| `arquivado` |
| `prioridade` | TEXT | `urgente` \| `alta` \| `normal` \| `baixa` |
| `categoria` | TEXT | `suporte` \| `vendas` \| `informacao` \| `spam` \| `outro` |
| `total_mensagens` | INT | Contador total de mensagens |
| `nao_lidas` | INT | Mensagens não lidas (zerado ao abrir a conversa) |
| `ultimo_msg_em` | TIMESTAMPTZ | Timestamp da última mensagem |
| `primeira_msg_em` | TIMESTAMPTZ | Timestamp da primeira mensagem |
| `resumo_ia` | TEXT | Resumo factual gerado pelo GPT-4o-mini |
| `resposta_sugerida` | TEXT | Rascunho de resposta gerado pela IA |
| `confianca_ia` | INT | Score 1-10 de confiança da triagem |
| `lead_id` | TEXT | ID do lead CRM vinculado (opcional) |
| `atribuido_a` | TEXT | Atendente responsável |
| `resolvido_em` | TIMESTAMPTZ | Quando foi resolvida |

#### `mensagens_inbox`
Mensagens individuais de cada thread.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Chave primária |
| `msg_id` | TEXT UNIQUE | ID de deduplicação |
| `conversa_id` | INT FK | Referência para `conversas.id` |
| `jid` | TEXT | JID do remetente |
| `de_mim` | BOOLEAN | `true` = enviada pelo atendente |
| `tipo` | TEXT | `text` \| `audio` \| `image` \| `document` \| `video` |
| `texto` | TEXT | Texto da mensagem |
| `transcricao` | TEXT | Transcrição do áudio (Whisper) |
| `duracao_audio_s` | REAL | Duração do áudio em segundos |
| `media_url` | TEXT | URL da mídia (se houver) |
| `status_proc` | TEXT | `pendente` \| `processado` \| `erro` |
| `enviado_em` | TIMESTAMPTZ | Timestamp original da mensagem |

---

### API REST — novos endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/inbox/stats` | Contadores: abertas, urgentes, não lidas, por categoria |
| `GET` | `/api/inbox/conversas` | Lista com filtros (status, categoria, prioridade, busca, paginação) |
| `GET` | `/api/inbox/conversas/{id}` | Conversa + mensagens; zera contador de não lidas |
| `PUT` | `/api/inbox/conversas/{id}` | Atualiza status, prioridade, categoria, etc. |
| `POST` | `/api/inbox/conversas/{id}/resolver` | Marca como resolvida |
| `POST` | `/api/inbox/conversas/{id}/arquivar` | Arquiva a conversa |
| `POST` | `/api/inbox/conversas/{id}/reabrir` | Reabre conversa resolvida/arquivada |
| `POST` | `/api/inbox/conversas/{id}/analisar` | Força nova triagem com IA |
| `POST` | `/api/inbox/conversas/{id}/responder` | Envia resposta via WhatsApp |

---

### Fluxo de processamento — mensagem recebida

```
Evolution API → POST /webhook/evolution
    ↓
normalize_evolution_payload()
    ↓
is_authorized_crm_group()
    ├─ É grupo CRM → fluxo CRM original (sem mudança)
    └─ É individual + INBOX_MODE_ENABLED=true
           ↓
       InboxService.process_incoming()
           ├─ get_or_create_conversa (upsert por JID)
           ├─ Transcrição de áudio (Whisper, se tipo=audio)
           ├─ add_mensagem_inbox (persistência)
           └─ asyncio.create_task(_triage_conversa)  ← não bloqueia resposta
                  ↓ (background)
              GPT-4o-mini → categoria, prioridade, resumo, sugestão
                  ↓
              update_conversa_triage (persiste no DB)
```

---

### Como ativar

1. No `.env` da aplicação, adicione:
   ```
   INBOX_MODE_ENABLED=true
   ```
2. Faça deploy normalmente. As tabelas são criadas automaticamente no startup.
3. O webhook da Evolution API continua sendo o mesmo (`POST /webhook/evolution`).
4. Acesse `/inbox` para ver as conversas.

---

### Configuração do Evolution API

Para que o inbox funcione, o webhook da Evolution API precisa estar configurado
para receber **todos os tipos de mensagem** do número, não apenas grupos.
No painel da Evolution, certifique-se de que o webhook está ativado para:
- `MESSAGES_UPSERT` (mensagens novas)
- Todos os tipos de chat (individual + grupos)

O modo CRM por grupo continua funcionando normalmente em paralelo.

---

## [Pré-MVP 2.0] — Histórico de melhorias do MVP 1.x

### Auto-send
- Loop multi-candidato (até 5 leads por ciclo) com marcação de `auto_erro`
- `reativar_leads_auto_erro()` para desbloquear números falhos após correção
- Aceita números fixos (10 dígitos) além de celulares: `_is_valid_br_phone()`
- Correção de timezone: `ZoneInfo(America/Sao_Paulo)` em todas operações de tempo
- `count_auto_sent_today` baseado na tabela `leads` (fonte de verdade)
- Badge `⚠️ Nº inválido` exibido nos cards de leads com falha

### Pipeline / CRM
- Interpretador de micro-updates via nomes (sem estruturar dados completos)
- Status override entre colchetes (`[qualificado]`, `[negociando]`, etc.)
- Fallback de contexto: usa último lead vinculado quando mensagem sem identidade
- Detecção de resultado de venda (ganho/perdido) via `crm_interpreter.py`
- Análise de conversa via `ANALISAR:` no grupo CRM

### Prospecção
- Busca de leads via OSM, Telelistas, Apontador
- Enriquecimento de WhatsApp por web scraping
- Fila de revisão (pendente/aprovado/descartado)
- Aprovação em lote com filtro por WhatsApp disponível

### Infraestrutura
- PostgreSQL como fonte de verdade (Google Sheets como backup write-only)
- Pool de conexões psycopg2 com retry
- `settings_kv` para configurações persistidas no banco
- Semáforo de webhook (máx 5 simultâneos)
