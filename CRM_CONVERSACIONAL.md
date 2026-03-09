# 💬 CRM Conversacional

Atualizar leads e consultar o CRM diretamente por linguagem natural no grupo do WhatsApp.

---

## 📍 Visão geral

Duas funcionalidades complementares:

1. **Micro-updates** — Atualizar status de leads com linguagem natural simples
2. **Queries** — Consultar leads e estatísticas em tempo real no grupo

Ambas evitam o pipeline complexo de LLM quando a intenção é clara.

---

## 🎯 Micro-updates

Atualize o status de um lead existente com uma mensagem curta, padrão verbal reconhecido.

### Como funciona

1. **Detecta padrão verbal** — Sistema reconhece frases como "respondeu", "quer demo", "mandei mensagem"
2. **Busca lead por nome** — Fuzzy matching sobre o banco (não cria lead novo)
3. **Atualiza status** — Se encontrado com confiança, atualiza status + prioridade
4. **Ambiguidade/sem match** — Responde de forma curta, pedindo clarificação

### Padrões reconhecidos

#### Nome vem antes do verbo

```
<NOME> respondeu               → status: em contato
<NOME> quer demo              → status: qualificado
<NOME> quer apresentacao      → status: qualificado
<NOME> está interessado       → status: qualificado
<NOME> nao usa whatsapp       → status: contato inválido
<NOME> nao tem interesse      → status: perdido
<NOME> sem interesse          → status: perdido
<NOME> numero errado          → status: contato inválido
<NOME> fechou                 → status: fechado
```

#### Verbo vem antes do nome

```
mandei mensagem pra <NOME>    → status: em contato
enviei mensagem pra <NOME>    → status: em contato
contatei o/a <NOME>          → status: em contato
liguei pra <NOME>            → status: em contato
```

### Exemplos

#### ✅ Acertos

```
"Clínica Sorriso respondeu"
↓
Lead encontrado: L0042 Clínica Sorriso
Status: novo → em contato
Resposta: ". Clínica Sorriso (L0042) → em contato"
```

```
"Odonto Prime quer demo"
↓
Lead encontrado: L0115 Odonto Prime Saúde
Status: em contato → qualificado
Resposta: ". Odonto Prime Saúde (L0115) → qualificado"
```

```
"Mandei mensagem pra Dr João Silva"
↓
Lead encontrado: L0003 Dr João Silva
Status: novo → em contato
Resposta: ". Dr João Silva (L0003) → em contato"
```

#### ⚠️ Ambiguidade

```
"Clínica respondeu"  (nome muito genérico)
↓
Múltiplos leads encontrados:
- L0042 Clínica Sorriso
- L0115 Clínica Odonto
- L0188 Clínica Popular
↓
Resposta: ". Mais de um lead encontrado: L0042 Clínica Sorriso | L0115 Clínica Odonto | L0188 Clínica Popular
Use VINCULAR <ID> para confirmar."
```

#### ❌ Sem match

```
"Clinica XYZ respondeu"
↓
Nenhum lead encontrado com esse nome
↓
Resposta: ". Não encontrei 'clinica xyz' com confiança suficiente para atualizar.
Verifique o nome ou use VINCULAR <ID>."
```

### Regras de detecção

- ✅ Padrão verbal reconhecido (ex: "respondeu", "quer demo")
- ✅ Nome entre 3 e 50 caracteres
- ❌ Sem telefone (indica field estruturado)
- ❌ Sem email (indica field estruturado)
- ❌ Sem URL ou @usuario (indica field estruturado)
- ❌ Sem score de telefone - o tamanho da mensagem **não** é critério primário (permite contexto curto e direto)

### O que acontece com o lead

```
Antes:
- status: "novo"
- prioridade: "media"
- ultima_interacao_em: "2026-02-15T10:30:00"

Micro-update: "Clínica Sorriso respondeu"

Depois:
- status: "em contato"           ← atualizado
- prioridade: "media"            ← recalculado
- ultima_interacao_em: "2026-03-09T14:25:00"  ← timestamp atual
- atividade registrada com tipo "respondeu"
```

---

## 🔍 Queries

Consulte leads e estatísticas em tempo real sem sair do grupo.

### Como funciona

1. **Detecta intenção de leitura** — Sistema reconhece perguntas como "leads de hoje", "quem respondeu"
2. **Executa query** — Busca no banco sem modificar dados
3. **Formata resposta** — Apresenta dados de forma legível no WhatsApp

### Tipos de queries

#### Leads criados hoje

```
Sua mensagem:  "leads de hoje" ou "leads de hoje?"
Resposta:      "Leads criados hoje: 3
               • L0042 Clínica Sorriso (dental) — novo
               • L0115 Odonto Prime (dental) — novo
               • L0188 Clinica Popular (geral) — novo"
```

#### Quem respondeu

```
Sua mensagem:  "quem respondeu" ou "quem me respondeu"
Resposta:      "Responderam nos últimos 7 dias: 5
               • L0001 Dr João (São Paulo) — em contato
               • L0042 Clínica Sorriso (Rio de Janeiro) — qualificado
               • L0115 Odonto Prime (Belo Horizonte) — em contato
               • L0188 Clínica Popular (Brasília) — qualificado
               • L0203 Med Center (São Paulo) — em contato"
```

**Nota:** Sempre menciona o período ("últimos 7 dias") para evitar ambiguidade.

#### Follow-ups vencidos

```
Sua mensagem:  "followup" ou "quem devo contatar"
Resposta:      "Follow-ups vencidos: 4
               • L0042 Clínica Sorriso | vence 2026-02-28 (enviar proposta)
               • L0115 Odonto Prime | vence 2026-03-01 (agendar demo)
               • L0188 Clínica Popular | vence 2026-03-02 (follow-up simples)
               • L0203 Med Center | vence 2026-03-04"
```

#### Pipeline (visão geral)

```
Sua mensagem:  "pipeline"
Resposta:      "Pipeline atual:
               • novo: 8
               • em contato: 12
               • qualificado: 5
               • negociando: 2
               • em espera: 3
               • sem resposta: 1
               • fechado: 4
               • perdido: 2"
```

#### Leads por status

```
Sua mensagem:  "leads qualificados" ou "leads novos"
Resposta:      "Leads qualificado: 5
               • L0001 Dr João (São Paulo)
               • L0042 Clínica Sorriso (Rio de Janeiro)
               • L0115 Odonto Prime (Belo Horizonte)
               • L0188 Clínica Popular (Brasília)
               • L0203 Med Center (São Paulo)"
```

### Padrões reconhecidos

| Padrão | Tipo | Período |
|--------|------|---------|
| "leads de hoje" | leads criados hoje | hoje |
| "quem respondeu" | responderam | últimos 7 dias |
| "quem me respondeu" | responderam | últimos 7 dias |
| "quem devo contatar" | follow-ups vencidos | - |
| "followup" | follow-ups vencidos | - |
| "pipeline" | visão geral por status | - |
| "leads qualificados" | por status | - |
| "leads novos" | por status | - |
| "leads em espera" | por status | - |

---

## 🛠️ Detalhes técnicos

### Arquitetura

```
Webhook WhatsApp
        ↓
   raw_text
        ↓
  [QUERY BRANCH] ← detect_query_intent() em crm_interpreter.py
        ↓
  is_message_too_vague?
        ↓
  [SPECIAL COMMANDS] ← VINCULAR, CORRIGIR, ANALISAR
        ↓
  [MICRO-UPDATE BRANCH] ← detect_micro_update() em crm_interpreter.py
        ↓
  [LLM PIPELINE] ← se nenhum ramo anterior capturou
```

### Modelos de dado

#### `MicroUpdate` (crm_interpreter.py)

```python
@dataclass
class MicroUpdate:
    candidate_name: str   # Nome a buscar
    status: str           # Status a aplicar
    activity_type: str    # Tipo de atividade a registrar
```

#### `QueryIntent` (crm_interpreter.py)

```python
@dataclass
class QueryIntent:
    type: str                        # "hoje" | "por_atividade" | "followup" | ...
    activity_type: Optional[str]     # para type="por_atividade"
    status: Optional[str]            # para type="por_status"
    days: int = 7                    # janela temporal
```

#### `FindByNameResult` (db_service.py)

```python
@dataclass
class FindByNameResult:
    lead: Optional[Dict]        # lead encontrado ou None
    candidates: List[Dict]      # candidatos em caso de ambiguidade
    score: float                # fuzzy match score
    is_exact: bool              # match único e confiante
    is_ambiguous: bool          # múltiplos candidatos próximos
```

### Funções principais

#### crm_interpreter.py

```python
def detect_micro_update(raw_text: str) -> Optional[MicroUpdate]:
    """Detecta padrão verbal simples para atualização de status."""
    # Retorna MicroUpdate ou None

def detect_query_intent(raw_text: str) -> Optional[QueryIntent]:
    """Detecta intenção de consulta ao CRM."""
    # Retorna QueryIntent ou None

def infer_status(text: str) -> Optional[str]:
    """Infere status a partir de texto (usado por micro-updates)."""
    # Retorna status ou None
```

#### db_service.py

```python
def find_lead_by_name(candidate_name: str, min_score: float = 0.85) -> FindByNameResult:
    """Busca lead por nome com fuzzy matching. Nunca cria lead novo."""
    # Fuzzy score >= 0.85 → match exato
    # Múltiplos candidatos próximos → ambiguidade
    # Caso contrário → sem match

def update_lead_status(lead_id: str, status: str, when: Optional[datetime]) -> None:
    """Atualiza status + prioridade pontualmente."""

def query_leads_today() -> Dict[str, Any]:
    """Leads criados hoje."""

def query_leads_by_activity_type(activity_type: str, days: int = 7) -> List[Dict]:
    """Leads com atividade específica nos últimos N dias."""

def query_leads_overdue_followup() -> List[Dict]:
    """Leads com follow-up vencido."""

def query_leads_by_status(status: str, limit: int = 10) -> List[Dict]:
    """Leads com status específico."""
```

#### main.py

```python
async def _execute_crm_query(intent, db: DBService) -> str:
    """Executa query e retorna texto formatado para WhatsApp."""

# No webhook handler:
# 1. Query branch (ANTES de is_message_too_vague)
# 2. Micro-update branch (ANTES do LLM)
```

---

## ✨ Boas práticas

### Para micro-updates

**✅ Faça:**
- Nome completo e claro: "Clínica Sorriso respondeu"
- Padrão verbal simples: "quer demo", "nao tem interesse"
- Uma ação por mensagem

**❌ Não faça:**
- Nome genérico: "clínica respondeu" (ambíguo)
- Texto muito longo: "clínica respondeu e disse que quer saber mais" (vai pro LLM)
- Múltiplos campos: "clínica sorriso respondeu, quer demo" (vai pro LLM)

### Para queries

**✅ Faça:**
- Perguntas simples e diretas: "leads de hoje", "quem respondeu"
- Frases curtas e sem contexto

**❌ Não faça:**
- Perguntas compostas: "quem respondeu nos últimos 3 dias" (período fixo é 7)
- Filtros complexos: "leads qualificados de São Paulo" (usa query simples, filtra depois)

---

## 🐛 Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| Micro-update não funciona | Nome muito genérico | Use nome completo ou VINCULAR <ID> |
| "Não encontrei com confiança" | Lead não existe ou nome errado | Verifique no dashboard ou crie o lead |
| Ambiguidade com 2 líderes | Fuzzy matching detectou múltiplos | Use VINCULAR <ID> para confirmar |
| Query retorna vazio | Nenhum lead corresponde aos critérios | Verifique os filtros |
| Texto muito longo não é micro | Esperado | Mensagens ricas vão para o LLM completo |

---

## 🔮 Próximas melhorias

- [ ] Micro-updates com múltiplos campos: "clínica X respondeu, quer demo, agendou para amanhã"
- [ ] Queries com filtros: "leads de hoje em São Paulo"
- [ ] Confirmar ambiguidade interativamente (multiple choice)
- [ ] Sugestões de ações: "Dr João não responde há 5 dias — fazer follow-up?"
- [ ] Histórico de micro-updates

---

**Última atualização:** 2026-03-09
