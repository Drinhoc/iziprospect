# IziClinic Invisible CRM (WhatsApp → OpenAI → Google Sheets)

CRM invisível para operação comercial da IziClinic: recebe webhook do Evolution API (texto/áudio), transcreve áudio com Whisper, extrai estrutura com LLM da OpenAI e persiste no Google Sheets.

## Arquitetura

1. `POST /webhook/evolution` recebe payload do Evolution.
2. Payload é normalizado para:
   - `msg_type`, `raw_text`, `media_url`, `timestamp`, `chat_id`, `is_group`
3. Se for áudio, baixa `media_url` e transcreve com `whisper-1`.
4. Envia texto para LLM (`gpt-4o-mini`) para extrair JSON estruturado.
5. Faz matching anti-duplicação no Sheets e upsert em `LEADS`.
6. Sempre grava entrada em `ATIVIDADES`.
7. Em ambiguidades, envia para aba `REVISAR`.

## Estrutura do projeto

```bash
app/
  main.py
  config.py
  schemas/models.py
  services/
    normalizer.py
    openai_service.py
    sheets_service.py
    evolution_service.py
Dockerfile
.env.example
requirements.txt
```

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

Copie `.env.example` para `.env` e preencha:

```bash
OPENAI_API_KEY=
GOOGLE_SHEETS_ID=
GOOGLE_SERVICE_ACCOUNT_JSON={...}
EVOLUTION_WEBHOOK_SECRET=
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
DEFAULT_TIMEZONE=UTC
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

## Testando webhook com curl

Exemplo texto:

```bash
curl -X POST http://localhost:8000/webhook/evolution \
  -H 'Content-Type: application/json' \
  -H 'x-webhook-secret: SEU_SECRET' \
  -d '{
    "data": {
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
      "messageTimestamp": 1730803200,
      "chatId": "5511999999999@g.us",
      "message": {"audioMessage": {"url": "https://seu-cdn/audio.ogg"}}
    }
  }'
```

## Comandos manuais no grupo

- `VINCULAR L0001`
  - Vincula a última atividade ao `lead_id`.
- `CORRIGIR L0001 cidade=Campinas segmento=Odonto`
  - Atualiza campos no lead.
- `SET L0001 whatsapp=+5511999999999 instagram=@clinicax`
  - Atualiza contatos do lead.

## Regras de matching implementadas

Prioridade:
1. `whatsapp`
2. `instagram`
3. `lead_key` (`cidade_normalizada:nome_normalizado`)
4. `contains` em `nome_normalizado` na mesma cidade
5. fuzzy fallback
   - `>=0.88`: match automático
   - `0.78-0.88`: não cria lead, envia para `REVISAR` com top 3
   - `<0.78`: cria lead novo

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

- Resposta de confirmação via Evolution API está implementada como best-effort (stub funcional opcional).
- Em caso de erro de entendimento/matching, dados podem cair em `REVISAR` para ajuste humano.
