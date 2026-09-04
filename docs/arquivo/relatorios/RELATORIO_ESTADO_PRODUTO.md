# Estado do Produto — EJC (Ecossistema Jurídico Clovis)

_Varredura anti-vitrine e mapa honesto do que está pronto. Gerado ao fim do ciclo de consolidação e construção dos verticais._

## Como foi verificado (não é auto-elogio)

- **Endpoints das ferramentas**: extraídos os 58 `endpoint:` das ferramentas de `ramosConfig.ts` e cruzados, um a um, com as rotas realmente montadas no `app.main`. Resultado: **0 endpoints quebrados** — toda ferramenta que aparece na tela responde no backend. Isso também é travado por teste de contrato (`test_calculadoras_ramos.py`), que **falha o CI** se alguém adicionar uma ferramenta sem endpoint.
- **Componentes premium**: cada flag de componente (`bancarioForense`, `tributarioFiscal`, `ambientalEstrategia`, `sociedadesCliente`, `lgpdRegistros`, `guia*`…) foi conferida contra o arquivo do componente e contra o render em `RamoBase.tsx`. Todos existem e são renderizados.
- **Endpoints premium (POST)**: abusividade/CET, XML fiscal, estratégia ambiental, ROPA/LGPD, societário, War Room, Diplomacia, verificador de citações e veredito de IA — todos montados e conferidos.
- **Suíte**: 621 testes passando, 26 skipped; `tsc --noEmit` e `vite build` limpos.

## Ramos jurídicos

Todos os ramos têm: cadastro de casos, análise de documento (upload + IA com HITL) e um conjunto de calculadoras determinísticas com **base legal e memória de cálculo** (nunca um número sem origem). Estado do diferencial premium por ramo:

| Ramo | Calculadoras | Diferencial premium | Guia operacional |
|---|---|---|---|
| **Bancário** | CET, taxas BACEN, revisional | **Motor de abusividade** (taxa vs média BACEN da modalidade/época, baliza REsp 1.061.530/RS) + expurgo Price → minuta revisional | ✅ |
| **Tributário** | 7 (auto de infração, prescrição/decadência, parcelamento, Simples, regimes, reforma, multa) | **Leitor de XML fiscal + recuperação de créditos** (Tema 69, monofásicos, ICMS-ST, prescrição) → PDF Visual Law | ✅ |
| **Ambiental** | 6 (auto de infração, crimes, TAC, licenciamento, reserva legal) | **Simulador de estratégia do auto** (pagar/converter/defender/prescrição, recomendação por menor desembolso) → requerimento de conversão | ✅ |
| **Empresarial** | societário | **Gestão societária de clientes** (cap table, eventos, due diligence, PII cifrada) | ✅ |
| **LGPD/Digital** | multa (art. 52), prazos | **ROPA (art. 37) + gerador de RIPD (art. 38)** por cliente, com análise de risco | ✅ |
| **Licitações** | habilitação (arts. 62-70), prazo de recurso, reajuste | **Auditor de propostas** (motor de 13 regras, Lei 14.133/21) → relatório de auditoria em PDF | ✅ |
| **Civil, Consumidor, Família, Trabalhista, Penal, Previdenciário, Trânsito, Imobiliário, Administrativo** | calculadoras específicas por ramo | análise de documento + guias | ✅ (maioria) |

## Ferramentas premium transversais

| Ferramenta | Estado | Nota de honestidade |
|---|---|---|
| **Núcleo Único de IA** (ai_gateway) | Real | Roteamento por task/complexidade, barreira de sanitização PII antes de provedor externo, HITL obrigatório, AILog sempre |
| **Verificador de jurisprudência** | Real | Dígito verificador CNJ, tetos de súmula, status verificada/identificada/suspeita; DataJud opt-in. Anti-alucinação determinístico |
| **Veredito de IA** (`/veredito_ia/analisar`) | Real | Jurimetria real (probabilidade nula se n<5), RAG de jurisprudência do escopo do cliente, citações verificadas anexadas; auth + acesso ao caso + rate limit |
| **Sala de Guerra / War Room** | Real | Simulação, sentinela, PDF Visual Law |
| **Diplomacia Digital** | Real | Cálculo de acordo, benchmarks de jurimetria, dossiê de pressão |
| **RAG / busca semântica** | Real (degrada com elegância) | Embeddings locais (fastembed); sem serviço, cai para busca textual sem quebrar |
| **Visual Law** | Real e unificado | Todos os 7+ geradores de PDF usam o tema dourado central; PDFs sempre em modo claro |

## Segurança e LGPD (padrão aplicado a todos os geradores de PDF novos)

Os quatro verticais construídos neste ciclo (Tributário, Ambiental, LGPD, Licitações-PDF) compartilham o **mesmo padrão endurecido**, auditado no Tributário e copiado nos demais:

- Escape anti-injeção (`esc()`) em **toda** string de payload antes do HTML do WeasyPrint;
- Download com `id` validado como UUID (sem path traversal);
- Retenção com TTL (varredura remove PDFs > 1h — dados de terceiros, LGPD);
- `rate_limit` em todas as rotas; limites de tamanho de payload (`Field(max_length)`);
- Upload de XML com parser seguro (`defusedxml` — XXE mitigado), leitura em blocos e teto agregado (anti-DoS de memória).

PII em repouso: `pii_crypto` (Fernet + HMAC + mascarado). Dados de sócios (societário) cifrados; ROPA de LGPD guarda **só metadado** de operação, nunca valor de titular.

## O que é honestamente PRELIMINAR (e por quê)

Nada disso é defeito — é a postura correta para software jurídico:

- Toda saída de IA e todo cálculo estratégico é **minuta/estimativa com aviso HITL**: a revisão do advogado é obrigatória (OAB).
- O simulador ambiental **não inventa faixas de multa** do Decreto 6.514 (variam por artigo) — só faz matemática sobre o valor informado, datas e constantes legais já vetadas.
- A recuperação de créditos tributários é **estimativa de triagem** — o valor exato depende de PGDAS/SPED/EFD.
- O auditor de licitações **sinaliza** pontos de impugnação por regras; não substitui a leitura técnica do edital.

## Pendências conhecidas (não bloqueiam uso)

- **Deploy com migrations**: o vertical LGPD (migration 072) exige rodar as migrations no servidor — o `atualizar-vps.sh` já faz.
- **Embeddings no servidor**: `.env` de produção ainda com `EMBEDDINGS_ENABLED=false` — ligar quando quiser busca semântica plena (degrada para textual até lá).
- **Licitações**: o auditor de propostas depende de frases auto-incriminatórias no texto do concorrente; evolução futura (maior rendimento) seria um leitor edital-vs-proposta, que exige IA e traz risco de alucinação — deliberadamente **não** feito por ora.
- Itens menores de infraestrutura (XFF/nginx, pré-baking do modelo de embeddings na imagem) permanecem no backlog P2/P3.

---
_Relatório determinístico, gerado a partir da varredura real das rotas montadas e dos componentes renderizados — não de uma lista de desejos._
