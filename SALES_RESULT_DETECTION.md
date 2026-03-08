# Detecção de Resultado de Venda

## 📋 Contexto

O sistema registra atividades de prospecção e relacionamento comercial enviadas pelo usuário via WhatsApp.

Além de criar leads, atividades e follow-ups, o sistema também deve identificar quando uma oportunidade foi concluída (ganho ou perdido) e atualizar o status correspondente.

---

## 🎯 Indicadores de venda ganha

Palavras-chave que indicam que a venda foi fechada:

- "fechou"
- "venda fechada"
- "cliente fechou"
- "negócio fechado"
- "contrato assinado"
- "virou cliente"
- "fechamos"
- "assinado"
- "aprovado"
- "confirmou"

---

## ❌ Indicadores de venda perdida

Palavras-chave que indicam que a oportunidade foi perdida:

- "não fechou"
- "perdemos"
- "cliente desistiu"
- "não avançou"
- "não deu negócio"
- "descartado"
- "parou"
- "não vai dar"
- "rejeitou"

---

## ✅ Ações ao detectar resultado

Quando um resultado é identificado:

1. **Atualizar status do lead:**
   - Venda ganha → `status = "fechado"`
   - Venda perdida → `status = "perdido"`

2. **Registrar atividade na timeline:**
   - Tipo: `"resultado"` ou similar
   - Ação: `"venda fechada"` ou `"oportunidade perdida"`
   - Resumo captura a mensagem do usuário

3. **Manter histórico completo:**
   - Nenhum dado é perdido
   - Pode-se reverter status se necessário (editando no dashboard)

---

## 📝 Exemplos

### Exemplo 1: Venda ganha
```
Usuário: "clínica sorriso fechou hoje"

Resultado:
├─ Lead: Clínica Sorriso
├─ Status: fechado
├─ Atividade: "Venda fechada — clínica sorriso fechou hoje"
└─ Tipo atividade: resultado
```

### Exemplo 2: Venda perdida
```
Usuário: "mercado oliveira não avançou"

Resultado:
├─ Lead: Mercado Oliveira
├─ Status: perdido
├─ Atividade: "Oportunidade perdida — mercado oliveira não avançou"
└─ Tipo atividade: resultado
```

### Exemplo 3: Sem resultado claro
```
Usuário: "falei com a clínica verde, eles gostaram"

Resultado:
├─ Lead: Clínica Verde
├─ Status: em contato (não muda)
├─ Atividade: normal (sem resultado registrado)
└─ Tipo atividade: contato
```

---

## 🔧 Implementação técnica

### Fluxo

```
mensagem do usuário
      ↓
[extract_structured_data] (OpenAI)
      ↓
[interpret_crm_message] (detecta resultado)
      ↓
resultado_venda = "ganho" | "perdido" | None
      ↓
if resultado_venda:
   ├─ status = "fechado" ou "perdido"
   ├─ activity.tipo = "resultado"
   └─ activity.resumo = "Venda fechada..." ou "Oportunidade perdida..."
      ↓
upsert_lead(status=new_status)
↓
add_activity(tipo="resultado", ...)
```

### Mudanças no código

**1. `crm_interpreter.py` — nova função:**
```python
def detect_sales_result(raw_text: str) -> Optional[str]:
    """
    Detecta resultado de venda na mensagem.
    Retorna: "ganho", "perdido", ou None
    """
    text = (raw_text or "").lower().strip()

    ganho_indicators = {
        "fechou", "venda fechada", "cliente fechou",
        "negócio fechado", "contrato assinado", "virou cliente",
        "fechamos", "assinado", "aprovado", "confirmou"
    }

    perdido_indicators = {
        "não fechou", "perdemos", "cliente desistiu",
        "não avançou", "não deu negócio", "descartado",
        "parou", "não vai dar", "rejeitou"
    }

    if any(ind in text for ind in ganho_indicators):
        return "ganho"
    if any(ind in text for ind in perdido_indicators):
        return "perdido"
    return None
```

**2. `interpret_crm_message()` — adicionar campo:**
```python
return InterpretedMessage(
    action_type="...",
    activity_type="...",
    confidence=...,
    followup_em=...,
    status_sugerido=...,
    resultado_venda=detect_sales_result(raw_text)  # NOVO
)
```

**3. `main.py` — webhook handler:**
```python
if interpretation.resultado_venda == "ganho":
    extracted.status_sugerido = "fechado"
    extracted.activity.tipo = "resultado"
    extracted.activity.resumo = "Venda fechada — " + extracted.activity.resumo
elif interpretation.resultado_venda == "perdido":
    extracted.status_sugerido = "perdido"
    extracted.activity.tipo = "resultado"
    extracted.activity.resumo = "Oportunidade perdida — " + extracted.activity.resumo
```

---

## 📊 Dashboard futuro (analytics)

Uma vez que isso estiver funcionando por alguns dias, o dashboard pode mostrar:

```
📈 Métricas deste mês

Leads totais: 32
├─ Ganhos: 7 (22%)
├─ Perdidos: 5 (16%)
└─ Em andamento: 20 (62%)

Taxa de conversão: 22% (7 ganhos / 32 leads)
```

---

## 🎯 Recomendações

### Fase 1 (agora)
- ✅ Detectar ganho/perdido
- ✅ Atualizar status automaticamente
- ✅ Registrar atividade com tipo "resultado"

### Fase 2 (depois)
- Dashboard com métricas simples
- Filtro por resultado (ganho/perdido/pendente)
- Análise de tempo até fechamento

### Fase 3 (futuro)
- Prompt LLM mais sofisticado para interpretar mensagens bagunçadas
- Detecção de valor de venda (se o usuário mencionar)
- Análise de motivos de perda

---

## 💡 Observação

Está funcionalidade não quebra o fluxo atual de prospecção. Apenas:
- Detecta resultado quando há
- Atualiza status apropriado
- Registra para análise futura

Zero complexidade adicional, máximo valor agregado.
