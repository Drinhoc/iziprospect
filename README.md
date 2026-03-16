# IziClinic Invisible CRM (WhatsApp → OpenAI → Google Sheets)

CRM invisível para operação comercial da IziClinic: recebe webhook do Evolution API (texto/áudio), transcreve áudio com Whisper, extrai estrutura com LLM da OpenAI e persiste no Google Sheets.

## Arquitetura

1. `POST /webhook/evolution` recebe payload do Evolution.
2. Payload é normalizado para:
   - `msg_id`, `msg_type`, `raw_text`, `media_url`, `timestamp`, `chat_id`, `is_group`
3. Filtro por grupo: ignora mensagens fora de grupo e fora de `CRM_TARGET_GROUP_ID`.
4. Idempotência: se `msg_id` já existir em `ATIVIDADES`, o webhook ignora duplicata (`{ "ok": true, "duplicate": true }`).
5. Triagem local ignora mensagens vagas (ex.: "ok", "teste") antes de chamar OpenAI.
6. Se for áudio, resolve mídia com `resolve_whatsapp_audio(media_url, mimetype)`, salva com extensão válida (ex.: `.ogg`) e transcreve com `whisper-1`.
7. Envia texto para LLM (`gpt-4o-mini`) para extrair JSON estruturado.
6. Faz matching anti-duplicação no Sheets e upsert em `LEADS`.
8. Sempre grava entrada em `ATIVIDADES` (incluindo `msg_id`).
9. Em ambiguidades/falhas reais, envia para aba `REVISAR`.

## Estrutura das abas

### LEADS
`lead_id, nome, cidade, segmento, whatsapp, instagram, site, status, ultima_interacao_em, proximo_followup_em, observacoes, nome_normalizado, cidade_normalizada, lead_key`

### ATIVIDADES
`data_hora, msg_id, lead_id, tipo, canal, mensagem_bruta, resumo, followup_em`

### REVISAR
`data_hora, mensagem_bruta, cidade_detectada, nome_detectado, candidatos, acao, resolvido_em`

## Logs e observabilidade

A aplicação usa `logging` padrão do Python com logs para:
- mensagem recebida
- `msg_id` extraído
- tipo de mensagem
- transcrição iniciada/finalizada
- duplicata ignorada
- lead resolvido / lead em revisão
- erro de transcrição
- erro de confirmação no WhatsApp (sem quebrar webhook)

## Comandos manuais no grupo

- `VINCULAR L0001`
  - MVP: vincula **a atividade mais recente não vinculada** (`lead_id` vazio).
- `CORRIGIR L0001 cidade=Campinas segmento=Odonto`
  - Atualiza campos no lead.
- `SET L0001 whatsapp=+5511999999999 instagram=@clinicax`
  - Atualiza contatos do lead.

## Pré-requisitos

- Python 3.11+
- Conta OpenAI com acesso a Whisper e Chat Completions
- Google Sheet e Service Account com permissão de edição
- Evolution API configurada para webhook

## Configuração do Google Sheets

1. Crie uma planilha no Google Sheets.
2. Copie o ID da planilha (`GOOGLE_SHEETS_ID`).
3. No Google Cloud, habilite **Google Sheets API**.
4. Crie uma **Service Account**.
5. Gere chave JSON.
6. Compartilhe a planilha com o e-mail da service account como Editor.
7. Use o JSON inteiro em `GOOGLE_SERVICE_ACCOUNT_JSON` (ou caminho para arquivo JSON).

> A aplicação cria/reinicializa automaticamente as abas `LEADS`, `ATIVIDADES`, `REVISAR` com os headers exigidos.

## Variáveis de ambiente


- `CRM_TARGET_GROUP_ID`: grupo autorizado do CRM (obrigatório em produção). Aceita formatos com/sem `@g.us` e até valor colado de markdown/mailto; o backend normaliza internamente. Mensagens fora do grupo alvo retornam `ignored` com `not_group` ou `unauthorized_group`.
- `DISABLE_EVOLUTION_CONFIRMATION`: quando `true`, não tenta envio de confirmação para Evolution (`confirmation skipped`).

## Importante sobre credencial Google no deploy

Para evitar crash de boot por JSON inválido em variável de ambiente:

- Prefira `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` no Railway (mais estável para escaping).
- Se usar `GOOGLE_SERVICE_ACCOUNT_JSON`, envie JSON válido com aspas duplas (`"`) e sem aspas simples de Python.
- O app agora tenta parse resiliente (JSON estrito, variação com `\n`, e fallback controlado), mas formato válido continua essencial.


Copie `.env.example` para `.env` e preencha:

```bash
OPENAI_API_KEY=
GOOGLE_SHEETS_ID=
GOOGLE_SERVICE_ACCOUNT_JSON={...}
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=
EVOLUTION_WEBHOOK_SECRET=
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
CRM_TARGET_GROUP_ID=
DISABLE_EVOLUTION_CONFIRMATION=true
# aliases opcionais de compatibilidade (caso sua infra use outro nome):
GROUP_ID_CRM_CONFIGURADO=
GROUP_ID_CRM=
CRM_GROUP_ID=
DEFAULT_TIMEZONE=UTC

# Auto-send (desligado por padrão — ativar explicitamente)
AUTO_SEND_ENABLED=false
AUTO_SEND_DIARIO_MAX=7
AUTO_SEND_HORA_INICIO=9
AUTO_SEND_HORA_FIM=18
AUTO_SEND_INTERVALO_MIN_S=180
AUTO_SEND_INTERVALO_MAX_S=720
```

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Testes recomendados (ordem segura)

1. Teste primeiro mensagens de **texto**.
2. Depois teste mensagens de **áudio**.

Isso reduz risco de troubleshooting misto (webhook + mídia + transcrição) no primeiro deploy.

## Testando webhook com curl

Exemplo texto:

```bash
curl -X POST http://localhost:8000/webhook/evolution \
  -H 'Content-Type: application/json' \
  -H 'x-webhook-secret: SEU_SECRET' \
  -d '{
    "data": {
      "key": {"id": "ABCD1234", "remoteJid": "5511999999999@g.us"},
      "messageTimestamp": 1730803200,
      "chatId": "5511999999999@g.us",
      "message": {"conversation": "Novo lead: Clínica Sorriso em Campinas, insta @sorriso"}
    }
  }'
```

Exemplo áudio:

```bash
curl -X POST http://localhost:8000/webhook/evolution \
  -H 'Content-Type: application/json' \
  -d '{
    "data": {
      "key": {"id": "EFGH5678", "remoteJid": "5511999999999@g.us"},
      "messageTimestamp": 1730803200,
      "chatId": "5511999999999@g.us",
      "message": {"audioMessage": {"url": "https://seu-cdn/audio.ogg"}}
    }
  }'
```

## Regras de matching implementadas

Prioridade:
1. `whatsapp`
2. `instagram`
3. `lead_key` (`cidade_normalizada:nome_canonico`)
4. `contains` em nome (mesma cidade)
5. fuzzy fallback
   - `>=0.88`: match automático
   - `0.78-0.88`: não cria lead, envia para `REVISAR` com top 3
   - `<0.78`: cria lead novo

A normalização remove acentos/pontuação e aplica limpeza leve de termos genéricos (ex.: clínica/consultório/odonto/estética) para melhorar proximidade de nomes.

## Docker

Build:

```bash
docker build -t iziclinic-crm .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env iziclinic-crm
```

## Deploy no Railway

1. Suba este repositório no GitHub.
2. Crie novo projeto no Railway (Deploy from GitHub).
3. Configure variáveis de ambiente do `.env.example`.
4. Railway detecta `Dockerfile` e faz build automático.
5. Configure URL pública no Evolution webhook apontando para:
   - `https://SEU_APP.railway.app/webhook/evolution`
6. (Opcional) Configure header `x-webhook-secret` no emissor e variável `EVOLUTION_WEBHOOK_SECRET`.

## Observações

- Falha de confirmação via Evolution API não quebra processamento do webhook.
- Em falha de transcrição ou mensagem não processável, o evento é roteado para `REVISAR`.


## Regras operacionais de robustez

- Mensagens vagas são ignoradas antes da OpenAI (`message_too_vague`) para reduzir custo e sujeira.
- Falha da OpenAI não quebra webhook: resposta HTTP 200 com `deferred=true` e `reason=openai_unavailable`.
- Matching prioriza telefone normalizado, depois instagram, depois nome/lead_key/fuzzy.
- `REVISAR` é usado para falhas reais (transcrição, ambiguidade, payload inválido), não para mensagens bobas ignoradas.


## Fluxo de áudio (WhatsApp)

- Nunca enviamos `.enc` diretamente para OpenAI.
- O backend usa `mimetype` para decidir extensão válida (`.ogg`, `.mp3`, `.wav`, etc.).
- A função `resolve_whatsapp_audio(media_url, mimetype)` baixa a mídia, cria arquivo temporário com extensão correta e retorna o `path` pronto para Whisper.
- Erros de áudio geram logs específicos (`falha_download_audio`, `mimetype_invalido`, `midia_nao_suportada`, `falha_transcricao`) e roteamento para `REVISAR`.


## Interpretação CRM (texto e áudio)

Após transcrever (quando áudio), o backend aplica interpretação CRM para classificar a ação:

- `novo_lead`
- `atualizar_lead`
- `registrar_atividade`
- `registrar_followup`
- `revisao_manual`

### Lógica de interpretação

1. Extrai telefone do texto (se houver).
2. Detecta follow-up (ex.: "amanhã", "semana que vem", "depois das 14").
3. Classifica tipo de atividade (respondeu, pediu proposta, sem interesse, número inválido etc.).
4. Se o LLM não trouxer nome, tenta fallback local com trecho anterior ao telefone.
5. Mantém intent segura (`update`) quando vier inválida/vazia.

### Pipeline final

receber evento
→ resolver áudio
→ transcrever
→ normalizar texto
→ interpretar intenção CRM
→ localizar lead (telefone > nome exato/semelhante > contexto)
→ registrar em LEADS / ATIVIDADES / REVISAR

### Exemplos de entrada/saída

Entrada: `"Clínica Sorriso, odonto, 19 99898-9888"`
- Ação esperada: `novo_lead`
- Resultado: upsert em LEADS + atividade `contato inicial`

Entrada: `"A clínica sorriso respondeu"`
- Ação esperada: `atualizar_lead` (ou `registrar_atividade` com contexto)
- Resultado: atividade `respondeu`

Entrada: `"Retornar amanhã"`
- Ação esperada: `registrar_followup`
- Resultado: `followup_em` preenchido

Entrada: `"Número errado"`
- Ação esperada: `registrar_atividade`
- Resultado: atividade `número inválido`, status sugerido de contato inválido

---

## Auto-Send: Envio Automático de Primeiro Contato

O sistema pode enviar automaticamente a primeira mensagem de prospecção para
leads com status `novo`. O envio é **desligado por padrão** e precisa ser
ativado explicitamente.

### Como funciona

```
Lead status='novo' + whatsapp preenchido
    │
    ▼ (a cada ~1 min o loop verifica)
Dentro da janela horária? (09h–18h) ──► não → aguarda
    │ sim
    ▼
Limite diário atingido? (padrão: 7/dia) ──► sim → aguarda amanhã
    │ não
    ▼
Seleciona 1 lead elegível (FIFO por data_criacao, preferência com segmento)
    │
    ▼
Gera mensagem personalizada (A/B/C determinístico por lead_id)
    │
    ▼
Envia via Evolution API (WhatsApp)
    │
    ├── Sucesso:
    │     • status → 'contato feito', temperatura → 'frio'
    │     • mensagem_enviada_em = agora
    │     • origem_primeiro_contato = 'automatico'
    │     • Registrado em atividades (tipo='auto_envio')
    │     • Registrado em msg_ab_eventos (evento='auto_enviada')
    │     • Loop dorme 3–12 min antes do próximo envio
    │
    └── Falha (API offline, número inválido):
          • Nada é alterado no lead
          • Retenta no próximo ciclo (60s)
```

### Como ativar

Defina no `.env`:

```bash
AUTO_SEND_ENABLED=true
AUTO_SEND_DIARIO_MAX=7        # quantos envios por dia
AUTO_SEND_HORA_INICIO=9       # hora de início (formato 24h)
AUTO_SEND_HORA_FIM=18         # hora de fim
AUTO_SEND_INTERVALO_MIN_S=180 # intervalo mínimo entre envios (segundos)
AUTO_SEND_INTERVALO_MAX_S=720 # intervalo máximo entre envios (segundos)
```

Reinicie a aplicação após alterar o `.env`. O loop começa imediatamente
na janela horária configurada.

### Quais leads são selecionados?

Um lead entra na fila de auto-send quando:

| Critério | Valor |
|---|---|
| `status` | `novo` |
| `whatsapp` | preenchido |
| `mensagem_enviada_em` | vazio (nunca enviado automaticamente) |
| `origem_primeiro_contato` | vazio (sem contato registrado) |

**Ordenação:** leads com `segmento` preenchido primeiro (para melhor
personalização da mensagem), depois por `data_criacao ASC` (mais antigos
na frente — FIFO).

Isso significa que leads sem WhatsApp, leads já contatados (manual ou
automaticamente), ou leads em qualquer status que não seja `novo` são
**automaticamente ignorados**.

### Variantes de mensagem (A/B/C)

Cada lead recebe sempre a mesma variante (determinística pelo `lead_id`):

| Variante | Estratégia |
|---|---|
| A | Apresentação pessoal casual ("Sou o Pedro...") |
| B | Dor-primeiro (abre com pergunta sobre o problema deles) |
| C | Prova social leve (menciona clínicas da região) |

Os templates são personalizados por segmento: `odontologia`, `medicina`,
`estetica`, `default` (demais casos).

### APIs de monitoramento

```bash
# Status atual do auto-send
GET /api/auto-send/status

# Histórico dos últimos 50 envios automáticos
GET /api/auto-send/historico
```

Exemplo de resposta de `/api/auto-send/status`:
```json
{
  "enabled": true,
  "diario_max": 7,
  "hora_inicio": 9,
  "hora_fim": 18,
  "enviados_hoje": 3,
  "restantes_hoje": 4,
  "proximos_leads": [
    { "lead_id": "L042", "nome": "Clínica Sorriso", "segmento": "odontologia" }
  ]
}
```

### Rastreamento e auditoria

Cada envio automático gera **3 registros**:

1. **`atividades`** — `tipo='auto_envio'`, `mensagem_bruta` contém o texto
   enviado, `canal='whatsapp_direto'`
2. **`msg_ab_eventos`** — `evento='auto_enviada'`, `variante=A/B/C`,
   permite medir taxa de resposta por variante
3. **`leads`** — campos `mensagem_enviada_em`, `auto_send_variante`,
   `origem_primeiro_contato='automatico'`

### Como pausar

Para pausar sem reiniciar a aplicação, basta mudar `AUTO_SEND_ENABLED=false`
e reiniciar. Leads com `mensagem_enviada_em` preenchido **não** serão
re-enviados.

### Diferença entre envio manual e automático

| | Manual | Automático |
|---|---|---|
| Quem dispara | Usuário copia a mensagem e envia no WhatsApp | Sistema envia direto |
| `origem_primeiro_contato` | `manual` | `automatico` |
| `mensagem_enviada_em` | não preenchido | preenchido com timestamp |
| Rastreado em `msg_ab_eventos` | sim (`evento='copiada'`) | sim (`evento='auto_enviada'`) |

### Logs

Procure no log da aplicação por:

```
auto_sender | enviando para lead_id=L042 nome='Clínica Sorriso' variante=B
auto_sender | OK | lead_id=L042 variante=B (3/7 hoje)
auto_sender_loop | aguardando 347s antes do próximo envio
auto_sender | limite diário atingido (7/7), aguardando amanhã
```
