# IziProspect — Visão de Produto Futuro (SaaS)

> Documento de referência para quando o IziProspect evoluir para SaaS.
> Não implementar agora — registrar a visão e revisitar na hora certa.
>
> **Atualizado:** Março 2026

---

## Princípio Central

**O IziProspect é e deve continuar sendo WhatsApp-first.**

```
90% das interações → WhatsApp
10% → dashboard (consulta, ajustes, configurações)
```

O dashboard não é onde o usuário trabalha no dia a dia.
Ele existe para revisar o pipeline, ajustar configurações e visualizar métricas.
O trabalho acontece no WhatsApp — e isso é o diferencial.

---

## Problema que as Configurações Resolvem

Cada negócio tem:
- Processos de venda diferentes
- Vocabulário diferente
- Ciclos de follow-up diferentes
- Perfis de cliente diferentes

Para que a IA interprete corretamente as conversas de cada negócio, o sistema precisa de um pequeno nível de contextualização. Mas sempre com defaults bons e configuração opcional — o usuário não deve precisar configurar nada para começar a funcionar.

---

## Filosofia de Design

| Princípio | O que significa |
|---|---|
| **Simples** | Configuração em poucos minutos, máximo 4 telas |
| **Opinativo** | O sistema já vem com defaults bons e funciona do zero |
| **Opcional** | Nada é obrigatório para começar — configurações desbloqueiam refinamento |

---

## Features de Configuração — Ordem de Prioridade

### ✅ PRIORIDADE 0 — Já implementado

#### Cadência de Follow-up (automática por status)

O sistema já sugere automaticamente a data de follow-up quando o status de um lead muda, sem o usuário precisar pedir.

**Regras atuais (hardcoded no código):**

| Status | Follow-up auto | Contexto gerado |
|---|---|---|
| Em contato | +2 dias | "retomar contato" |
| Qualificado | +2 dias | "avançar proposta" |
| Em espera | +5 dias | "cobrar retorno" |
| Negociando | +2 dias | "fechar negociação" |
| Sem resposta | +30 dias | "tentar nova abordagem" |

**Para o SaaS:** esses valores viram editáveis por workspace no painel de configurações. Estruturalmente, só precisam sair de constantes no código e ir para uma tabela `workspace_settings` no banco. A lógica de aplicação já existe.

---

### 🔴 PRIORIDADE 1 — Multi-tenancy (pré-requisito de tudo)

Antes de qualquer configuração por cliente, o banco precisa de isolamento por workspace.

**O que muda tecnicamente:**
- Tabela `workspaces` com `workspace_id`, plano, configurações
- Todas as tabelas recebem coluna `workspace_id`
- Autenticação de usuários (Supabase Auth ou Clerk — simples de integrar)
- Webhook da Evolution API roteia para o workspace correto pelo número

**Estimativa:** 2–3 semanas de trabalho focado. É o maior esforço, mas desbloqueia tudo que vem depois.

---

### 🟡 PRIORIDADE 2 — Contexto do Negócio para IA

**Problema:** A IA hoje interpreta conversas de forma genérica. Para uma clínica, "agenda" significa reunião; para um corretor, pode ser visita. Contexto de negócio melhora muito a precisão.

**Como funciona:** O usuário descreve o negócio em 3 campos simples:

| Campo | Exemplo |
|---|---|
| Tipo de negócio | Clínica odontológica |
| Produto/serviço | Software de automação para clínicas |
| Perfil do cliente | Clínicas pequenas e médias, donos e gerentes |

Esse contexto é injetado automaticamente no início do prompt da IA:

```
Você está analisando conversas de prospecção para uma empresa que vende
[produto] para [perfil de cliente] no segmento de [tipo de negócio].
```

**O que muda tecnicamente:** Uma linha adicionada ao `PROMPT` em `openai_service.py`, lida do banco. Simples — a infraestrutura de prompt já existe.

**Onde no dashboard:** Tela de configurações → "Sobre seu negócio" → 3 campos de texto.

---

### 🟡 PRIORIDADE 3 — Cadência de Follow-up Editável

Tornar configurável no painel os prazos que hoje são hardcoded.

**Interface simples:**

```
┌──────────────────────────────────────────┐
│ Configuração de follow-up automático     │
├───────────────┬──────────────────────────┤
│ Em contato    │ [ 2 ] dias               │
│ Qualificado   │ [ 2 ] dias               │
│ Em espera     │ [ 5 ] dias               │
│ Negociando    │ [ 2 ] dias               │
│ Sem resposta  │ [ 30 ] dias              │
└───────────────┴──────────────────────────┘
```

**O que muda tecnicamente:** Os valores saem de `_STATUS_FOLLOWUP_RULES` em `crm_interpreter.py` e vão para a tabela de configurações do workspace. `suggest_followup_from_status()` lê do banco em vez de constantes.

---

### 🟢 PRIORIDADE 4 — Pipeline Customizável (com cuidado)

Permitir que o usuário ajuste os status do pipeline — mas com limites claros para não quebrar a lógica interna.

**O que o usuário pode fazer:**
- Renomear status (ex: "Qualificado" → "Com interesse")
- Adicionar até 2 status intermediários customizados
- Reordenar a sequência de exibição no funil

**O que o usuário NÃO pode fazer:**
- Remover os status estruturais (`novo`, `fechado`, `perdido`, `arquivado`)
- Ter mais de 12 status no total (limite de complexidade)

**Nota técnica importante:** Hoje os status são hardcoded em múltiplos lugares (regex do `crm_interpreter.py`, guia do prompt da IA, badge map no JS, CSS). Status customizados são a feature mais complexa tecnicamente. Requer:
1. Abstração dos status para o banco
2. Geração dinâmica do prompt da IA com os status do workspace
3. Sincronização com o frontend

**Recomendação:** Só implementar depois de validar com 50+ clientes reais. Alta complexidade, valor incerto sem dados de uso real.

---

### 🟢 PRIORIDADE 5 — Palavras-chave de Contexto

Campo opcional para refinar a interpretação da IA com vocabulário do negócio.

**Exemplo:**
```
agenda, consulta, paciente, dentista, plano odonto, convênio
```

**O que faz:** As palavras são adicionadas ao prompt como "glossário do segmento", ajudando a IA a identificar intenções específicas do negócio.

**Nota:** O Contexto do Negócio (Prioridade 2) já resolve 80% disso. Esta feature é complementar e de baixa prioridade.

---

## Mapa de Dependências

```
Multi-tenancy (P1)
  ↓
  ├── Contexto do Negócio (P2) — independente tecnicamente, mas precisa de auth
  ├── Cadência editável (P3) — precisa de workspace_id para salvar config
  ├── Pipeline customizável (P4) — mais complexo, precisa de tudo acima
  └── Palavras-chave (P5) — fácil, mas sem multi-tenant não faz sentido
```

---

## O Que NÃO Adicionar (pelo menos até 200 clientes)

| Feature | Por quê não |
|---|---|
| Múltiplos pipelines por workspace | Complexidade alta, valor incerto |
| Regras de automação visuais (tipo Zapier) | Foge do escopo do produto |
| Personalização de IA por lead individual | Custo operacional explodiria |
| Campos customizados no lead | Aumenta complexidade do dashboard, do banco e do prompt |
| SLA e regras de escalação | Feature de CRM enterprise, não do Izi |

---

## Evolução Natural do Produto

```
Fase 1 — Agora
  Uso pessoal, refinamento, validação da proposta de valor
  Follow-up automático ✅, status refinados ✅, prospecção ✅

Fase 2 — Primeiros clientes SaaS
  Multi-tenancy + auth + wizard de onboarding
  Sem configurações customizadas ainda — defaults bons resolvem

Fase 3 — Configurações básicas
  Contexto do negócio (P2) + cadência editável (P3)
  Depois de validar com 20–50 clientes reais

Fase 4 — Personalização avançada
  Pipeline customizável (P4) se dados mostrarem que é necessário
  Só implementar se múltiplos clientes pedirem ativamente
```

---

## Resumo em Uma Frase

> O IziProspect deve ser uma ferramenta que funciona perfectamente com zero configuração,
> e fica ainda melhor com 10 minutos de setup — nunca o contrário.

---

*Documento atualizado em Março 2026 — revisitar ao iniciar Fase 2 (primeiros clientes SaaS)*
