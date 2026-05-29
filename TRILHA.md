# TRILHA — por onde retomar o IziDesk

> Documento de entrada para retomar o desenvolvimento. Última revisão: 2026-05-29.
> Branch de trabalho: `claude/mvp-2-iziprospect-saas`.

---

## 1. Onde o projeto está

O IziDesk é uma plataforma de **inbox WhatsApp com IA + CRM**, multi-tenant, hospedada
por nós (nós hospedamos o Evolution API de todos os clientes).

Status por área:

| Área | Estado | Observação |
|------|--------|------------|
| Inbox MVP 2.0 (triagem IA, transcrição, sugestão) | ✅ Pronto | Inbound puro — nunca inicia contato |
| CRM por grupo (modo 1.x) | ✅ Pronto | Coexiste com o inbox |
| Dashboard inbox-first | ✅ Pronto | UI ainda single-tenant (ver §3) |
| Multi-tenancy (schema-per-tenant) | 🟡 Metade | **Só a ingestão (webhook) é tenant-aware** |
| Admin panel (`/admin`) | ✅ Pronto | Criar tenant, QR code, status WhatsApp |
| Auth de operador / login do cliente | ❌ Não feito | Adiado para pós-MVP (decisão do dono) |
| Billing (cobrança/planos) | ❌ Não feito | A definir como vender/receber |
| Onboarding self-service | ❌ Não feito | Hoje o admin cria o tenant na mão |

---

## 2. O que foi feito na última sessão (revisão geral)

Revisão completa do código com foco em bugs. Corrigido (commit `4737019`):

- **Triagem IA:** valida `categoria`/`prioridade` contra o enum permitido (valores
  fora do conjunto poluíam o banco e quebravam a ordenação da UI); `confianca`
  tolera retorno não-numérico do modelo.
- **Áudio sem transcrição:** grava placeholder legível em vez de mensagem vazia.
- **`get_admin_overview`:** cursor novo por tenant — um schema faltando não aborta
  mais a agregação inteira.
- **`TenantDBService._conn/_put`:** rollback + commit em volta do `SET search_path`,
  evitando conexão "idle in transaction" e vazamento de schema entre tenants no pool.
- **Webhook:** processamento de inbox protegido por try/except → retorna 200 (a
  dedupe por `msg_id` já evita duplicatas) em vez de 500, que causaria reentrega
  em loop pela Evolution.
- **Admin:** comparação de token timing-safe (`hmac.compare_digest`); valida
  `WEBHOOK_BASE_URL`; reverte tenant órfão se a criação do schema falhar.
- **Hardening barato:** limites em `search`/`page` do inbox; log de `mediaKey`
  malformada no normalizer.

---

## 3. ⚠️ A LACUNA PRINCIPAL — UI ainda é single-tenant

**Este é o item nº 1 para resolver quando voltar.**

A multi-tenancy só foi conectada na **ingestão**: o webhook lê o `instanceName`,
descobre o tenant e grava no schema certo (`TenantDBService`). Mas tudo que o
**operador vê e usa** ainda aponta para o banco global (schema `public`) e para a
instância Evolution global:

- `app/routers/api_inbox.py` → `_get_db()` usa `get_db_service()` (global) e
  `_get_inbox_svc()` usa o `evolution_service` global.
- `app/routers/dashboard_ui.py`, `api_leads.py`, `api_prospeccao.py` → idem.

**Consequências enquanto isso não for resolvido:**
- Com **1 cliente**, funciona se o webhook gravar no mesmo schema que a UI lê.
  Na prática a UI lê o `public`, mas o webhook grava em `tenant_x` → **os dados
  do cliente não aparecem na UI** a menos que o tenant seja o `public`.
- Responder pela UI sai pela instância Evolution **errada** (a global), não a do
  tenant.

**Como resolver (depende de auth — ver §4):**
1. Introduzir contexto de tenant por request (cookie de sessão do operador →
   `tenant_id`).
2. Trocar `_get_db()`/`_get_inbox_svc()` para resolver `TenantDBService` e uma
   `EvolutionService` por tenant (mesma lógica já existente no webhook em
   `main.py:585-611` — dá para extrair num helper compartilhado).
3. Aplicar o mesmo em dashboard/leads/prospecção.

> Atalho de teste sem auth: para validar 1 cliente end-to-end agora, dá para
> apontar a UI a um tenant fixo via env var temporária e instanciar
> `TenantDBService.from_pool(...)` nos routers. **Gambiarra de teste, não produção.**

---

## 4. Roadmap pós-MVP (ordem sugerida)

```
AUTH  →  UI tenant-aware (§3)  →  Onboarding self-service  →  Billing
```

1. **Auth de operador** (a peça que destrava tudo)
   - Login por tenant (cada cliente acessa só o próprio inbox).
   - Sessão → `tenant_id` no request. Reaproveitar o padrão de cookie do admin
     (`admin_ui.py`) como base.

2. **UI tenant-aware** — §3 acima. Sai quase de graça depois do auth.

3. **Onboarding self-service**
   - Cliente cria conta → cria tenant + schema + instância Evolution → exibe QR.
   - Toda a mecânica de instância/QR já existe em `api_admin.py` e
     `evolution_service.py`; falta a tela self-service e o cadastro.

4. **Billing**
   - Definir modelo de cobrança (Stripe é o caminho natural).
   - `plano` já existe em `public.tenants` — ganchos prontos para limites por plano.

---

## 5. Dívidas técnicas menores (não urgentes)

- **Métodos de leitura não dão commit** (padrão de todo o `DBService`): conexões
  voltam ao pool "idle in transaction". Não trava nada na escala atual, mas o
  ideal é commit/rollback ao final de cada leitura.
- **`_tenant_db_cache` (main.py)** nunca expira. Se um tenant for deletado, o
  objeto fica em memória. Impacto desprezível; limpar ao deletar tenant seria limpo.
- **Validação de `evolution_instance`**: hoje aceita qualquer string no cadastro.
  Vale um regex (`^[a-zA-Z0-9_-]+$`) por higiene.
- **Auto-Send / Prospecção**: pertencem ao modo CRM 1.x e estão desligados no
  inbox (`inbox_mode_enabled`). Genericizados na rebrand, mas os templates podem
  ser ajustados ao público-alvo real quando houver cliente.

---

## 6. Variáveis de ambiente necessárias

```
# Core
OPENAI_API_KEY=...
DATABASE_URL=postgres://...
EVOLUTION_API_URL=https://seu-evolution...
EVOLUTION_API_KEY=...              # chave da instância (single-tenant / fallback)
EVOLUTION_WEBHOOK_SECRET=...       # opcional, valida header do webhook

# Inbox MVP 2.0
INBOX_MODE_ENABLED=true

# Multi-tenant / Admin
ADMIN_TOKEN=<senha forte>          # protege /admin e /api/admin
EVOLUTION_GLOBAL_API_KEY=...       # chave server-level do Evolution (criar/deletar instância)
WEBHOOK_BASE_URL=https://app...    # URL pública do app (p/ registrar webhook das instâncias)
```

---

## 7. Mapa rápido de arquivos

| Arquivo | Papel |
|---------|-------|
| `app/main.py` | Webhook + roteamento multi-tenant + loops de background |
| `app/services/db_service.py` | DBService + `TenantDBService` + tenants CRUD (fim do arquivo) |
| `app/services/inbox_service.py` | Processamento do inbox + triagem IA |
| `app/services/evolution_service.py` | Envio + gestão de instâncias WhatsApp |
| `app/routers/api_inbox.py` | API REST do inbox (⚠️ ainda single-tenant — §3) |
| `app/routers/api_admin.py` | API REST do admin (tenants, QR, status) |
| `app/routers/admin_ui.py` | Páginas `/admin` |
| `app/templates/admin_*.html` | UI do admin panel |

Para detalhes de produto/arquitetura completos: `README.md` e `CHANGELOG.md`.
