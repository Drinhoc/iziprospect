# Melhorias Implementadas no IziProspect CRM

## 📋 Resumo
Implementadas 6 melhorias principais no sistema de CRM para prospecção de clínicas:
- Pendência inteligente e consistente
- Colunas reorganizadas no Sheets
- Prompts melhorados para resumo e pendência
- Sincronização bidirecional Sheets↔DB
- Fix para áudios sequenciais
- Confirmação interativa no WhatsApp quando há dúvida

---

## 1. **Pendência Proativa** 🎯

**Problema:** Campo `pendencia` era extraído inconsistentemente — às vezes desaparecia quando não havia menção explícita.

**Solução:**
- Prompt OpenAI agora é mais agressivo e inclui exemplos por status
- **Fallback automático:** Se OpenAI retorna `null` mas o status implica ação, inferimos automaticamente:
  - `novo` → "Fazer primeiro contato"
  - `em contato` → "Fazer follow-up"
  - `qualificado` → "Enviar proposta"
  - `proposta enviada` → "Aguardar retorno"
  - `negociando` → "Fechar contrato"

**Resultado:** Campo `pendencia` **sempre** preenchido quando há ação pendente.

**Onde:** `app/main.py` (linhas ~402-405) + `app/services/openai_service.py` (PROMPT linha 56-60)

---

## 2. **Colunas Reorganizadas** 📊

**Problema:** Ordem das colunas era ruim — informações importantes (status, whatsapp) espalhadas.

**Ordem Anterior:**
```
lead_id | nome | cidade | segmento | whatsapp | email | instagram | site | responsavel | fonte |
status | prioridade | data_criacao | ...
```

**Nova Ordem (lógica e intuitiva):**
```
lead_id* | nome | status | prioridade | whatsapp | email | instagram | segmento | cidade |
responsavel | fonte | site | ultima_interacao_em | proximo_followup_em | data_criacao |
pendencia | resumo | observacoes | [campos_ocultos]
```

**Migração Automática:** No próximo startup, o Sheets é **reordenado automaticamente** sem perda de dados.

**Onde:** `app/services/sheets_service.py` (LEADS_HEADERS linha 21-41 + método `_reorder_sheet_columns` linha 63-78)

---

## 3. **Prompts Melhorados** 🤖

### 3.1 Resumo do Lead (`LEAD_SUMMARY_PROMPT`)

**Antes:** Genérico demais.
```
"Escreva um resumo em 1-2 frases (máx 180 chars)"
```

**Depois:** Estruturado e comercial.
```
Formato: "[Nome/Tipo] em [cidade] — [último acontecimento] — [próximo passo]"

Exemplos:
- "Clínica Sorrir (odonto) em SP — proposta enviada em mar/26 — aguardar retorno do Dr. Paulo."
- "Studio Estética em BH — qualificado, alta prioridade — enviar proposta esta semana."
```

**max_tokens:** 80 → 100 (para comportar resumos mais ricos)

**Onde:** `app/services/openai_service.py` (LEAD_SUMMARY_PROMPT linha 81-88)

### 3.2 Extração de Pendência (`PROMPT`)

Agora inclui tabela de status → pendência e exemplos mais realistas.

**Onde:** `app/services/openai_service.py` (linha 56-60)

---

## 4. **Sync Sheets→DB Automático** 🔄

**Problema:** Edições manuais no Sheets não refletiam no DB (era one-way: DB→Sheets).

**Solução:** Sistema de sincronização automática a cada 15 minutos + endpoint manual.

### Como funciona:
1. **Background loop:** Asyncio polling a cada 15 min (configurável via `SHEETS_SYNC_INTERVAL_MINUTES`)
2. **Lê o Sheets** → **Atualiza o DB** com edições do usuário
3. Campos sincronizados: `nome`, `status`, `prioridade`, `whatsapp`, `email`, `instagram`, `segmento`, `cidade`, `responsavel`, `fonte`, `site`, `observacoes`, `proximo_followup_em`
4. **Não sobrescreve:** campos automáticos (`data_criacao`, `ultima_interacao_em`, `resumo`, `pendencia`)

### Endpoint manual (acionamento imediato):
```bash
curl -X POST http://localhost:8000/sync/sheets-to-db \
  -H "x-webhook-secret: SEU_SECRET"
```

**Onde:**
- Background loop: `app/main.py` (linhas 66-88)
- Endpoint: `app/main.py` (linhas 212-218)
- Lógica de atualização: `app/services/db_service.py` (método `update_lead_from_sheets` linha 614-650)
- Config: `app/config.py` (linha 48) + `.env.example`

---

## 5. **Fix: Áudios Sequenciais** 🎙️

**Problema:** Segundo áudio complementar (sem nome/telefone) criava novo lead fantasma em vez de vincular ao primeiro.

**Solução:** Detecção inteligente de identidade de lead.

```python
# Se a mensagem NÃO tem identificador (nome/tel/email/instagram),
# skip no upsert → vai direto ao fallback de contexto →
# → vincula ao último lead da conversa
```

**Resultado:** Áudios sequenciais sempre vincular ao **mesmo lead**.

**Onde:** `app/main.py` (linhas ~425-460)

---

## 6. **Pergunta no WhatsApp quando há Dúvida** ❓

**Problema:** Quando o match era ambíguo (score 0.78–0.88), silenciosamente ia para REVISAR.

**Solução:** Bot manda mensagem no grupo pedindo confirmação.

### Exemplo:
```
. Dúvida: esta mensagem é sobre qual lead?
L0001 Clínica Sorrir | L0042 Clínica Sorrir SP | L0089 Sorrir Odonto

Responda: VINCULAR L0001 (ou o ID correto) — ou ignore se for lead novo.
```

**Como:** Aproveita o comando `VINCULAR L{id}` já existente. Operador vê no grupo e responde.

### Regra crítica:
> **Todas as mensagens do bot DEVEM começar com `.` (ponto)**
>
> Isso garante que o filtro anti-loop (`main.py:245`) ignore a própria resposta do bot.

**Onde:** `app/main.py` (linhas ~546-575)

---

## 📝 Verificação Rápida

Testar as 6 melhorias:

1. **Pendência:** Envie "Clínica X qualificada" → deve aparecer pendencia "Enviar proposta"
2. **Colunas:** Verifique aba LEADS — deve estar: nome, status, prioridade, whatsapp bem destacados
3. **Prompt resumo:** Verifique formato dos resumos no DB/Sheets (deve ter "em [cidade] — ...")
4. **Sync Sheets→DB:** Edite status no Sheets → aguarde 15min OU chame `/sync/sheets-to-db` → verifique DB
5. **Áudios sequenciais:** Envie 2 áudios seguidos (1º "Clínica X, odonto" + 2º "e tem instagram @clinica") → ambos vinculam a L0001
6. **Dúvida no WhatsApp:** Envie mensagem ambígua → bot deve perguntar no grupo qual lead é

---

## ⚙️ Configuração

### Variáveis de ambiente

```env
# Intervalo de sync automático Sheets→DB (minutos)
SHEETS_SYNC_INTERVAL_MINUTES=15
```

Default: 15 minutos. Mude para 30 ou 60 se quiser sincronizar menos frequentemente.

---

## 📚 Arquivos modificados

| Arquivo | O que mudou |
|---------|-------------|
| `app/services/openai_service.py` | Prompts melhorados (pendência + resumo) |
| `app/services/sheets_service.py` | Coluna reordenada + migração automática |
| `app/services/db_service.py` | `update_lead_from_sheets()` + `upsert_lead` retorna tuple |
| `app/main.py` | Fallback pendência + contexto sequencial + sync loop + pergunta WhatsApp + endpoint |
| `app/config.py` | `SHEETS_SYNC_INTERVAL_MINUTES` |
| `.env.example` | Novo env var |

---

## 🚀 Deploy

1. **Pull** do branch `claude/analyze-project-XnE4G`
2. **Restart** a aplicação — as mudanças entram em vigor:
   - Novo prompt OpenAI
   - Colunas reordenadas no próximo acesso ao Sheets
   - Background loop de sync iniciado
3. **Testar** as 6 verificações acima

---

**Tudo funcionando? Legal! 🎉**
