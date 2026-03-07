# IziProspect — Análise Completa de Viabilidade como SaaS

> **Versão:** 1.0 | **Data:** Março 2026
> **Contexto:** Produto funcional em fase de teste pessoal, com plano de escala comercial

---

## O Que É o IziProspect (Reposicionado)

**IziProspect é um CRM de prospecção conversacional via WhatsApp.**

O vendedor fala (áudio ou texto) no grupo do WhatsApp → a IA estrutura automaticamente → os dados aparecem em tempo real no dashboard com o resumo do dia, pendências e funil.

**Não é um CRM para clínicas. É um CRM para qualquer vendedor ativo.**

```
Sem app extra. Sem data entry manual. Sem planilha perdida.
Só WhatsApp → IA → Dashboard.
```

### O Produto Hoje
| Componente | Tecnologia | Função |
|---|---|---|
| Interface | WhatsApp (Evolution API) | Operador envia áudios/textos |
| IA | OpenAI (GPT-4o) | Transcreve, extrai, resume, infere |
| Banco | PostgreSQL | Source of truth, histórico |
| Visualização | Google Sheets | Dashboard e edição manual |
| Backend | FastAPI (Python) | Orquestração e lógica |

---

## 1. Mercado

### Quem é o Usuário

**Qualquer vendedor que faz prospecção ativa:**
- Corretores de imóveis
- Vendedores de seguros / planos de saúde
- SDRs e closers de startups B2B
- Representantes comerciais
- Gestores de vendas de clínicas, academias, cursos
- Freelancers que prospectam clientes
- Donos de pequenas empresas que vendem diretamente

### Tamanho do Mercado (Brasil)

| Segmento | Vendedores Ativos (est.) | % Usa WhatsApp para prospecção |
|---|---|---|
| Corretores imóveis | ~420.000 | ~85% |
| Vendedores seguros/planos | ~180.000 | ~80% |
| SDRs/Inside Sales | ~90.000 | ~70% |
| Representantes comerciais | ~200.000 | ~75% |
| PMEs com time de vendas | ~1.500.000 | ~60% |
| **Total Estimado** | **~2.400.000** | **~70%** |

- **TAM:** ~2.4M vendedores ativos no Brasil
- **SAM (dispostos a pagar por ferramenta):** ~240.000 (10%)
- **SOM realista em 3 anos:** ~3.000–10.000 clientes

### Por Que o Timing É Bom

1. **WhatsApp é o CRM real do vendedor brasileiro** — mas é caótico
2. **IA virou mainstream** — vendedores estão abertos a assistentes inteligentes
3. **Concorrentes ainda não resolveram a interface conversacional** bem
4. **Custo de IA caiu 80%** em 2 anos — margens ficaram viáveis

---

## 2. Proposta de Valor

### Problema Real

Vendedores ativos perdem informação o tempo todo:

```
- "Quem eu liguei hoje mesmo?"
- "Qual era o status daquele lead que mandei áudio?"
- "Preciso fazer follow-up de quem essa semana?"
- "Quanto prospectuei esse mês?"
```

Hoje eles resolvem isso com:
- Planilha manual (esquece de atualizar)
- CRM caro (não usa porque é complicado)
- Memória + notas no celular (perde tudo)
- Grupos bagunçados de WhatsApp (sem estrutura)

### Solução IziProspect

```
1. Vendedor manda áudio/texto no grupo WhatsApp normalmente
2. IA transcreve, extrai: nome, telefone, status, pendência
3. Lead é criado/atualizado no CRM automaticamente
4. Confirmação chega no grupo: ". CRM atualizado — João Silva (L0042)"
5. Dashboard mostra: resultado do dia, funil, pendências, follow-ups
```

**Resultado:** Vendedor não muda hábito (continua usando WhatsApp) mas agora tem CRM completo funcionando invisível.

### Diferencial Único

> **"O único CRM que o vendedor não percebe que está usando."**

Nenhum concorrente tem isso. Todos exigem que o vendedor abra um app, preencha campos, clique em salvar. O IziProspect captura tudo passivamente.

---

## 3. Modelo de Negócio

### Planos Propostos

```
╔══════════════════════════════════════════════════════════════╗
║  PLANO SOLO — R$ 79/mês (ou R$ 790/ano)                     ║
╠══════════════════════════════════════════════════════════════╣
║  • 1 vendedor / 1 número WhatsApp                           ║
║  • Até 300 leads ativos                                     ║
║  • Dashboard pessoal (resultado do dia, funil, pendências)  ║
║  • Resumo diário automático via WhatsApp                    ║
║  • Sincronização Google Sheets incluída                     ║
╚══════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════╗
║  PLANO EQUIPE — R$ 249/mês (ou R$ 2.490/ano)                ║
╠══════════════════════════════════════════════════════════════╣
║  • Até 5 vendedores / 3 grupos WhatsApp                     ║
║  • Leads ilimitados                                         ║
║  • Dashboard por vendedor + visão gerencial                 ║
║  • Relatório semanal de desempenho                          ║
║  • Ranking e metas da equipe                                ║
║  • Suporte por email                                        ║
╚══════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════╗
║  PLANO EMPRESA — R$ 799/mês (ou R$ 7.990/ano)               ║
╠══════════════════════════════════════════════════════════════╣
║  • Até 20 vendedores / grupos ilimitados                    ║
║  • CRM white-label (sua marca no dashboard)                 ║
║  • API completa para integrações                            ║
║  • Webhooks customizáveis                                   ║
║  • Customização de prompts/regras por segmento              ║
║  • Suporte por WhatsApp prioritário                         ║
║  • Onboarding assistido (call 1h)                           ║
╚══════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════╗
║  PLANO ENTERPRISE — Sob consulta (R$ 2.000–8.000/mês)       ║
╠══════════════════════════════════════════════════════════════╣
║  • Time de vendas grande (20+ vendedores)                   ║
║  • Modelo IA fine-tuned no segmento do cliente              ║
║  • Integração com CRM existente (HubSpot, Salesforce, RD)   ║
║  • SLA 99.9%, suporte dedicado                              ║
║  • Compliance LGPD + relatórios de auditoria                ║
╚══════════════════════════════════════════════════════════════╝
```

### Monetização Complementar

| Add-on | Preço | Descrição |
|---|---|---|
| Grupo extra | +R$ 49/mês | 1 número/grupo adicional |
| Relatório BI exportável | +R$ 29/mês | Excel/PDF avançado |
| Integração CRM externo | +R$ 79/mês | HubSpot, RD Station, Pipedrive |
| SMS de follow-up | +R$ 39/mês | Envio automático de lembretes |

---

## 4. Projeção Financeira

### Ano 1 (Validação + Primeiros Clientes)

| Plano | Clientes | MRR |
|---|---|---|
| Solo | 40 | R$ 3.160 |
| Equipe | 10 | R$ 2.490 |
| **Total** | **50** | **R$ 5.650/mês** |
| **ARR** | | **R$ 67.800/ano** |

Custo mensal estimado: R$ 3.500 (infra + OpenAI + ferramentas)
**Lucro líquido Ano 1: ~R$ 26k** *(bootstrapped, sem salários)*

---

### Ano 2 (Escala com Vendas)

| Plano | Clientes | MRR |
|---|---|---|
| Solo | 200 | R$ 15.800 |
| Equipe | 60 | R$ 14.940 |
| Empresa | 15 | R$ 11.985 |
| **Total** | **275** | **R$ 42.725/mês** |
| **ARR** | | **R$ 512.700/ano** |

Custos Ano 2: R$ 180k (1 dev, 1 vendedor, infra)
**Lucro líquido Ano 2: ~R$ 330k**

---

### Ano 3 (Consolidação)

| Plano | Clientes | MRR |
|---|---|---|
| Solo | 600 | R$ 47.400 |
| Equipe | 150 | R$ 37.350 |
| Empresa | 40 | R$ 31.960 |
| Enterprise | 5 | R$ 20.000 |
| **Total** | **795** | **R$ 136.710/mês** |
| **ARR** | | **R$ 1.640.520/ano** |

Custos Ano 3: R$ 600k (time 5 pessoas, infra, marketing)
**Lucro líquido Ano 3: ~R$ 1M**

---

## 5. Concorrência

### Mapa Competitivo

| Concorrente | Foco | Preço | Como o Izi Vence |
|---|---|---|---|
| **Pipedrive** | Funil visual | R$ 100–275/mês | Sem WhatsApp, sem IA, data entry manual |
| **HubSpot** | CRM completo | R$ 300–1.500/mês | Caro, complexo, não é para vendedor ativo |
| **RD Station** | Inbound + CRM | R$ 147–299/mês | Foco em inbound, não prospecção ativa |
| **Agendor** | CRM leve BR | R$ 99–399/mês | Sem IA, sem WhatsApp nativo |
| **Moskit** | CRM vendas BR | R$ 79–299/mês | Sem transcrição/IA, interface tradicional |
| **Kommo (amoCRM)** | CRM WhatsApp | R$ 150–400/mês | Mais caro, não é conversacional/passivo |
| **ChatGPT + Sheets** | DIY manual | R$ 0–120/mês | Não automatizado, não é CRM, exige setup |

### Posição Estratégica

```
                    ┌─────────────────────────────────────┐
               Caro │ HubSpot    Salesforce                │
                    │            Zendesk                   │
                    │                                      │
                    │ RD Station  Pipedrive  Kommo         │
                    │                                      │
             Barato │ Agendor  Moskit  ✅IZIPROSPECT       │
                    └─────────────────────────────────────┘
                      Genérico ←————————→ WhatsApp + IA
```

**O IziProspect ocupa o quadrante que ninguém tem:** Barato + WhatsApp nativo + IA passiva.

---

## 6. Potencial da Ideia

### Pontos Fortes ✅

**1. Interface Zero Atrito**
Vendedor não aprende nada novo. Já usa WhatsApp. Só continua usando.
ROI imediato: elimina 3–6h/semana de data entry por vendedor.

**2. Dados Passivos = Dados Reais**
CRMs tradicionais têm problema de adoção (vendedor não preenche).
Aqui os dados são capturados naturalmente → dados mais ricos e completos.

**3. IA Aplicada em Contexto Certo**
Transcrição de áudio → extração estruturada → resumo cumulativo é uma cadeia de valor real.
Não é IA "por moda", é IA que resolve problema concreto.

**4. Produto já Funciona**
Você tem backend, integração WhatsApp, IA, DB e sync em produção.
A maioria das startups leva 12–18 meses para chegar aqui. Você chegou.

**5. Margens Altas**
Custo por usuário: ~R$ 0,05–0,20/dia (OpenAI + infra)
Receita por usuário: R$ 2,60–26,60/dia
**Margem bruta potencial: 85%+**

**6. Stickiness Natural**
CRM acumula dados históricos. Quanto mais tempo o cliente usa, mais difícil é sair.
Churn esperado: 3–5%/mês (bom para SaaS B2B)

---

### Pontos Fracos ⚠️

**1. Dependência de Terceiros Críticos**
- OpenAI: mudança de preço ou rate limit afeta custo/desempenho
- Google Sheets: quota pode ser atingida com escala
- Evolution API (WhatsApp): risco de instabilidade/ban
- **Mitigação:** Planejar abstração de cada dependência

**2. WhatsApp Não É Oficial Como CRM**
A Meta não endossa uso de WhatsApp Business API para esse padrão.
Risco baixo (não é spam), mas existe.
**Mitigação:** Usar WABA (WhatsApp Business API oficial) via parceiros Meta

**3. Onboarding Ainda Complexo**
Setup atual exige: instância Evolution, grupo configurado, variáveis de ambiente.
Para escala, precisa de wizard de 5 minutos.
**Mitigação:** Wizard de onboarding no-code (prioridade alta)

**4. Dashboard é Google Sheets**
Funciona para MVP mas não é escalável nem profissional.
Para vender para empresas médias, precisa de dashboard próprio.
**Mitigação:** React dashboard (roadmap Ano 1)

**5. Sem Diferenciação de Marca Ainda**
Nome "IziProspect" / "IziClinic" precisa de identidade clara.
**Mitigação:** Branding consistente antes de escala

---

## 7. Riscos e Problemas Potenciais

### Técnicos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Ban de instância WhatsApp | Média | Alto | Migrar para WABA oficial |
| OpenAI indisponível | Baixa | Médio | Queue + retry + fallback regras |
| Sheets quota excedida | Alta (escala) | Alto | Dashboard próprio (prioridade) |
| Latência alta em horário de pico | Média | Médio | Semáforo já implementado, escalar workers |
| Dados do cliente vazados | Baixa | Crítico | LGPD, criptografia, audits |

### Negócio

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Concorrente grande lança similar | Média | Alto | Velocidade + nicho defendido |
| CAC alto demais | Média | Alto | Conteúdo orgânico + word-of-mouth |
| Churn alto por falta de engajamento | Média | Alto | Relatório diário automático via WhatsApp |
| Clientes pedem features fora do escopo | Alta | Médio | Roadmap público, priorização clara |
| Dificuldade de precificação | Baixa | Médio | Teste A/B de preços no lançamento |

---

## 8. Sugestões de Melhoria

### Roadmap Recomendado

#### Fase 0 — Hoje (Produto Atual)
```
✅ Backend FastAPI funcional
✅ Transcrição de áudio via OpenAI
✅ Extração estruturada (nome, telefone, status, pendência)
✅ Sync bidirecional PostgreSQL ↔ Sheets
✅ Confirmação automática no grupo
✅ Contexto sequencial de conversa
✅ Comandos: CORRIGIR, VINCULAR, SET
```

#### Fase 1 — Validação (Meses 1–3)
```
□ Wizard de onboarding (5 min do zero até primeiro lead)
□ Resumo diário automático via WhatsApp (7h/18h)
□ Multi-tenant: isolamento por cliente no banco
□ Plano de preços testado com 10 clientes reais
□ Landing page simples com caso de uso
□ Métricas básicas: leads/dia, taxa de captura, churn
```

#### Fase 2 — Dashboard Próprio (Meses 4–8)
```
□ Dashboard React/Next.js substituindo Sheets
   - Resultado do dia (leads novos, atividades, fechamentos)
   - Funil de prospecção visual
   - Pendências e follow-ups do dia
   - Histórico de cada lead com linha do tempo
□ API pública documentada (Swagger)
□ Webhook de eventos para integrações externas
□ Login e gestão de usuários (Auth0 ou Supabase Auth)
```

#### Fase 3 — Inteligência e Escala (Meses 9–18)
```
□ Score de lead automático (quente/morno/frio)
□ Sugestão de próximo passo por lead
□ Previsão de fechamento baseada em histórico
□ Relatório de desempenho semanal por vendedor
□ Integração nativa com Pipedrive, HubSpot, RD Station
□ Suporte a múltiplos idiomas (EN para expansão LATAM)
□ Fine-tuning por segmento (imóveis, seguros, SaaS B2B)
```

#### Fase 4 — Plataforma (Meses 18+)
```
□ Marketplace de integrações
□ Templates de prospecção por segmento
□ White-label para agências e consultorias de vendas
□ App mobile (PWA primeiro, depois nativo)
□ Módulo de treinamento (IA avalia qualidade das abordagens)
```

---

## 9. Go-to-Market Strategy

### Fase 1: Tração Orgânica (Meses 1–3)

**Canal A — Uso Pessoal Público**
- Use IziProspect na sua prospecção real
- Documente resultados: "Fiz X leads hoje sem digitar nada"
- Poste no LinkedIn, Instagram, Twitter/X
- *Meta: 500 seguidores interessados*

**Canal B — Comunidades de Vendas**
- Grupos Facebook/WhatsApp de corretores, SDRs, representantes
- Demonstração ao vivo: grave tela do áudio → lead capturado → Sheets
- *Meta: 20 leads quentes por mês*

**Canal C — Beta Privado Pago**
- Convide 10 pessoas para beta a R$ 49/mês
- Foco em feedback, não em receita
- Cada beta = 1 case study potencial
- *Meta: 10 clientes pagantes, NPS > 50*

**Custo: R$ 0 (só tempo)**

---

### Fase 2: Aceleração (Meses 4–8)

**Canal A — Conteúdo SEO**
- Blog: "como fazer CRM pelo WhatsApp", "como organizar leads de imóveis"
- YouTube: demo de 3 min → lead capturado em tempo real
- *Meta: 1.000 visitas/mês orgânicas*

**Canal B — Outbound Ativo**
- Scrape de SDRs/corretores no LinkedIn
- Mensagem WhatsApp personalizada: "Vi que você prospecta [segmento]..."
- Demo call de 20 min com tela compartilhada
- *Meta: 50 conversas/mês, 10% conversão = 5 clientes/mês*

**Canal C — Parcerias Estratégicas**
- Consultorias de vendas (treinadores de SDR, coaches comerciais)
- Eles indicam para base de clientes, ganham 20–30% comissão
- *Meta: 2–3 parceiros, 30–50 clientes por parceiro*

**Investimento: R$ 3–5k/mês (ads + ferramentas)**

---

### Fase 3: Escala (Meses 9–18)

**Canal A — Inbound Machine**
- Case studies publicados (antes/depois com dados reais)
- Webinars mensais: "Como montar CRM no WhatsApp"
- Parceria com influenciadores de vendas

**Canal B — Inside Sales**
- Contratar 1 SDR dedicado (R$ 4–5k/mês)
- Foco em Equipe e Empresa (ticket > R$ 249)
- *Meta: 15 novos clientes/mês*

**Canal C — Revendas**
- Agências de marketing que atendem PMEs
- Ferramentas de automação (Make, n8n) como canal de indicação

---

## 10. Análise SWOT

```
┌─────────────────────────────┬─────────────────────────────┐
│         FORÇAS              │        FRAQUEZAS            │
├─────────────────────────────┼─────────────────────────────┤
│ • Interface zero atrito     │ • Dashboard ainda no Sheets │
│ • IA aplicada corretamente  │ • Onboarding complexo       │
│ • Produto funcional hoje    │ • Dependência OpenAI/Google │
│ • Margens brutas 85%+       │ • Sem branding definido     │
│ • Stickiness por dados hist.│ • Time de 1 pessoa          │
├─────────────────────────────┼─────────────────────────────┤
│      OPORTUNIDADES          │        AMEAÇAS              │
├─────────────────────────────┼─────────────────────────────┤
│ • 2.4M vendedores no Brasil │ • Concorrente replicar      │
│ • WhatsApp = padrão BR      │ • OpenAI mudar pricing      │
│ • IA ainda novidade p/ PMEs │ • Meta restringir WABA      │
│ • Expansão LATAM (ES/PT)    │ • Churn por falta dashboard │
│ • White-label p/ agências   │ • CAC alto sem conteúdo     │
└─────────────────────────────┴─────────────────────────────┘
```

---

## 11. Avaliação Honesta

### Notas por Dimensão

| Dimensão | Nota | Justificativa |
|---|---|---|
| **Diferencial de produto** | 9/10 | Genuinamente único no mercado BR |
| **Tamanho de mercado** | 8/10 | 2.4M vendedores, TAM real e grande |
| **Potencial de lucro** | 8/10 | 85%+ margem bruta, escalável |
| **Facilidade de vender** | 7/10 | ROI claro, mas onboarding ainda difícil |
| **Stickiness / retenção** | 8/10 | Dados históricos = difícil de sair |
| **Complexidade técnica** | 6/10 | Muitas dependências, precisa amadurecer |
| **Velocidade de execução** | 9/10 | Produto pronto, sem precisar de time grande |
| **Potencial de saída** | 7/10 | Aquisição por HubSpot/RD/Agendor em 5 anos |

**Média geral: 7.75/10**

---

### Tipo de Empresa Que Pode Virar

**Cenário Conservador (80% de probabilidade):**
> Bootstrapped SaaS B2B com 500–1.000 clientes, R$ 1–2M ARR, fundador + 3–5 pessoas.
> Lucro de R$ 400k–1M/ano. Sustentável, ótimo estilo de vida, possível saída por aquisição.

**Cenário Otimista (30% de probabilidade):**
> Com parcerias estratégicas (Agendor, RD, iClinic), expansão LATAM e white-label:
> 5.000–10.000 clientes, R$ 8–15M ARR.
> Atrai investimento anjo ou seed (R$ 2–5M) para escalar time.

**Cenário Pessimista (20% de probabilidade):**
> Dificuldade de onboarding + churn alto + concorrente grande replicando =
> Produto vira ferramenta pessoal sem escala comercial.

---

## 12. Plano de Ação Imediato

### Os Próximos 90 Dias (Fase de Validação)

```
SEMANAS 1–2: Preparação para o mercado
├── Deploy em produção com domínio próprio
├── Criar landing page simples (1 página com demo em vídeo)
├── Configurar multi-tenant básico (isolamento por cliente)
└── Definir planos e preços finais

SEMANAS 3–6: Primeiros 10 clientes pagantes
├── Contatar 50 vendedores ativos (LinkedIn/WhatsApp direto)
├── Oferecer beta pago: R$ 49/mês por 3 meses
├── Fazer onboarding manual (call 30 min + suporte direto)
└── Coletar feedback semanal estruturado

SEMANAS 7–12: Validação e ajuste
├── Medir: NPS, churn, leads capturados/semana, tempo economizado
├── Documentar 3 case studies com dados reais
├── Ajustar prompt/extração com base em erros reais
└── DECISÃO: produto validado? → Fase 2 | Não? → Pivotar/ajustar

CRITÉRIOS DE SUCESSO:
✅ 10 clientes pagantes ativos
✅ NPS > 45
✅ Churn < 10% no período
✅ Pelo menos 1 cliente que indica outro espontaneamente
```

### Se Validar → Fase 2 (Meses 4–8)

```
Prioridade 1: Dashboard React próprio (substitui Sheets)
Prioridade 2: Wizard de onboarding (zero to hero em 5 min)
Prioridade 3: 1 canal de aquisição funcionando (outbound OU conteúdo)
Prioridade 4: Migrar para WABA oficial (segurança)
Meta: 50 clientes pagantes, R$ 15k MRR
```

---

## 13. Recomendações Finais

### ✅ FAÇA

1. **Valide com 10 clientes reais ANTES de construir mais features**
   O produto já resolve o problema. Antes de dashboard novo, tenha 10 pessoas pagando.

2. **Gravar um demo de 3 minutos e postar agora**
   Áudio → lead capturado → confirmação → Sheets. Em 3 min. Sem edição.
   Esse vídeo vai vender mais do que qualquer texto.

3. **Cobrar desde o dia 1**
   Beta não precisa ser grátis. R$ 49/mês filtra quem quer de verdade.

4. **Priorize onboarding acima de novas features**
   Se o cliente demora mais de 15 min para configurar, ele desiste.

5. **Use o resumo diário como feature principal de retenção**
   Todo dia às 18h, o vendedor recebe: "Você fez 8 leads hoje. 3 pendentes."
   Isso cria hábito e justifica a mensalidade sozinho.

### ❌ NÃO FAÇA

1. **Não busque VC para essa ideia agora**
   Mercado de 2.4M mas SOM inicial de 3–10k clientes não justifica VC.
   Bootstrapped é o caminho certo aqui.

2. **Não construa dashboard antes de ter clientes pagantes**
   Sheets é feio mas funciona. Valide o problema antes de investir em UI.

3. **Não tente ser CRM genérico competindo com HubSpot**
   Você não vai ganhar no feature-set. Ganhe na experiência WhatsApp + IA.

4. **Não escale marketing antes de product-market fit**
   Cada cliente que churna sem dar feedback é dinheiro e dado perdido.

5. **Não espere o produto estar "perfeito" para mostrar**
   O produto já é suficientemente bom. A hora de mostrar é agora.

---

## Conclusão

**O IziProspect tem fundação sólida para virar um negócio real.**

Você construiu algo que resolve um problema concreto (data entry de leads) de uma forma que nenhum concorrente faz (WhatsApp passivo + IA). O mercado é grande o suficiente para um bootstrapped SaaS lucrativo, com potencial de R$ 1–2M ARR em 3 anos.

O maior risco não é técnico nem competitivo. É execução: onboarding fácil o suficiente, e distribuição consistente o suficiente, para converter interesse em clientes pagantes recorrentes.

**Se 10 pessoas pagarem R$ 79/mês e continuarem após 3 meses, escale. Se não, entenda por quê antes de investir mais.**

A fase 1 que você está fazendo (teste pessoal → mostrar para pessoas) é exatamente a estratégia certa.

---

*Análise gerada em Março 2026 | IziProspect v1.0*
