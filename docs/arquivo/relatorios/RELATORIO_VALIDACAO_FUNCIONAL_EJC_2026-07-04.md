# Relatório de Validação Funcional — EJC — 2026-07-04

Auditoria cética de funcionamento REAL (3 agentes em paralelo, somente leitura),
seguindo o fio completo tela → API → serviço → fonte de dados. Critério: "existe
arquivo" NÃO é "funciona". Evidências arquivo:linha nos relatórios dos agentes;
aqui, a síntese e o plano de correção.

Legenda: ✅ funcional real · 🟡 parcial · 🔴 placeholder/quebrado/órfão

---

## 1. Fundamentos (dados básicos & RAG)

| Item | Veredito | Detalhe |
|---|---|---|
| OCR (PDF nativo + escaneado + XML/NF-e) | ✅ | PyMuPDF + pytesseract por página; parser XML anti-XXE. Lacuna: `.xlsx/.xls/.doc` são aceitos no upload mas **não têm extrator** → `ocr_text` vazio silencioso |
| Extração estruturada → preencher caso/cliente | 🟡 | O fio ponta a ponta EXISTE e é real (analisar → pré-preencher form → resolver cliente → aplicar-extracao materializa partes/áreas/nº). MAS **CPF/CNPJ/nº de processo são mascarados pela LGPD antes do LLM** → esses campos voltam sempre vazios. Correção: extrair por regex determinística no texto cru ANTES da sanitização |
| GED (upload/download/classificar/excluir) | ✅ | Zero mocks; magic bytes, IDOR-checks, cofre de confidencialidade, audit LGPD, classificação HITL |
| RAG | 🟡 | Ingestão/chunks/isolamento por cliente reais e testados (32 testes). Em produção (embeddings OFF) a busca degrada para AND-ILIKE de até 8 termos — recall péssimo. Correções: ativar embeddings local (já entregue no PR #33) e melhorar o fallback para pg_trgm/FTS |
| Clientes / Casos / Prazos / Financeiro / Portal | ✅ | PII cifrada, visibilidade RBAC, alertas de prazo com scheduler REAL (7/3/1 dias, sino sempre; e-mail/WhatsApp/push exigem flags no .env), cálculos financeiros em Decimal com SQL real, portal isolado com mensagens bidirecionais |

**Nenhum dado enlatado encontrado nos 5 fluxos** — as lacunas são de extração
ausente por tipo de arquivo, mascaramento PII e feature flags de produção.

## 2. Fase 4 — Ferramentas premium

| Ferramenta | Veredito | Detalhe |
|---|---|---|
| Jurimetria agregada | ✅ | Estatística real do banco com honestidade estatística (n mínimo=5 exposto) |
| **Veredito IA** | 🔴 **CRÍTICO** | Probabilidade por heurística fixa (+0.2 se "licitação") e **jurisprudência FAKE hardcoded** ("Jurisprudência relevante 1", link1.com) — **com tela ativa no frontend**. Único módulo fake com UI. Corrigir ou remover JÁ |
| Sala de Guerra (painel do caso) | ✅ | 100% SQL real |
| IA Sentinela (>60d / >30d) | 🟡 | Queries reais; job roda às segundas mas alertas **só vão para o log** — ninguém é notificado. Correção: usar `criar_notificacao_interna` (padrão já existente no monitor DOU) |
| War Room (simular parte contrária) | 🟡 | IA real via gateway, **endpoint órfão** (nenhuma tela chama) |
| Visual Law PDF | 🟡 | Gera PDF real; bug de singleton (páginas acumulam entre chamadas) e sem download/tela |
| Diplomacia (calculadora VPL) | 🟡 | Fórmula real; **Selic hardcoded 10,75%** (usar API do BCB); prob./tempo não puxam da jurimetria |
| Dossiê de Pressão | 🔴 | Monta o prompt e **nunca chama a IA** — retorna frase fixa |
| Monitor DOU (scheduler) | ✅ | HTTP real ao in.gov.br diário às 6h, dedup, vínculo a caso, notificação + e-mail |
| Radar legislativo | 🟡 | API real da Câmara (1 página, keywords fixas); Senado nunca implementado; sem tela |
| Motor Estratégico / Minerador de Sucesso | 🔴 | Código morto/órfão (um deles chama método inexistente). O papel real é cumprido por `case_intel.aprendizado_encerramento` ✅ |

**Padrão recorrente:** a "tríade v3" tem backend parcialmente real mas **nenhuma
tela chama os endpoints** — módulos registrados como entregues, inacessíveis ao usuário.

## 3. Fase 5 — Verticais por ramo

**Achado central: ~20 de ~52 calculadoras da UI apontam para endpoints
INEXISTENTES (404 ao clicar)** — todo o grupo Licitações do ramo Administrativo,
6/7 tributárias, 5/5 ambientais, 4 cíveis, taxas-BACEN "ao vivo" do bancário e
verbas rescisórias trabalhista (que existe em outro path). As que existem são
reais. Implementar cada uma é ~30 linhas no molde de `ramos.py`.

| Vertical | Estado real | Alicerce |
|---|---|---|
| Bancário | ✅ ~70% | Comparador BACEN com API real do BCB; extratos OFX/CSV/PDF → 8 regras com base legal → minuta revisional SSE ponta a ponta |
| Empresarial | 🟡 ~40% | CRUD + 3 calcs reais + contratos com alertas de vencimento; falta societário-cliente (quotas) e due diligence |
| Trabalhista/Penal/Cível etc. | 🟡 | Calculadoras majoritariamente reais + guias; 5 cards 404 |
| Ambiental | 🟡 ~30% | Backend REAL de autos de infração (prazo automático Dec. 6.514/08) **órfão sem tela**; 5 calcs 404 |
| Licitações | 🟡 ~15% | "Auditor" = 3 palavras-chave fixas; checklist habilitação 404; skill_router cosmético |
| Tributário | 🔴 ~10% | Guia rico + 1 calc; XML fiscal/PIS-COFINS/PER-DCOMP inexistentes |
| LGPD produto | 🔴 ~5% | 2 calcs; sem diagnóstico para cliente (o compliance interno ✅ é outra coisa) |

A "análise documental por ramo" existe e não é prompt único (prompts específicos
por área em `analise_bancaria.py:AREA_PROMPTS`) — diferenciação por prompt, não
por regra codificada.

---

## Plano de correção priorizado

### P0 — Confiabilidade (não pode esperar)
1. **Veredito IA**: reescrever para delegar ao orchestrator (task jurimetria) +
   jurisprudência do RAG interno — ou desregistrar router e remover a aba.
2. **Calculadoras 404** (~20): implementar no molde existente ou remover os cards.

### P1 — Destravar valor já construído (barato)
3. Extração de CPF/CNPJ/nº CNJ por **regex no texto cru** antes da sanitização
   (destrava o preenchimento automático completo do intake).
4. Sentinela: alertas → `criar_notificacao_interna` (sino) em vez de log.
5. Ligar telas aos endpoints órfãos: War Room na página Sala de Guerra, ambiental
   (`/environmental`) na tela do ramo, análise de impacto/radar na Inteligência.
6. Selic via API do BCB (série 432) com fallback em setting; VPL pré-preenchido
   com benchmarks da jurimetria.
7. Visual Law PDF: instância por request + FileResponse.
8. Ativar embeddings local em produção (PR #33) + melhorar fallback textual (pg_trgm).
9. Completar `gerar_dossie_pressao` (prompt já existe — chamar o gateway).
10. `.xlsx/.xls/.doc`: adicionar extrator ou avisar "sem indexação" no upload.

### P2 — Higiene
11. Deletar código morto: `motor_estrategico`, `minerador_sucesso`,
    `gatilhos_estruturais`, stub `radar_poder.monitorar_dou`.
12. Esconder botões no-op da Jurimetria ("Treinar", "Ingerir DataJud").

### Construção dos verticais (ordem por alicerce real)
Bancário (completar) → Empresarial (+ Guia Operacional do dono como
`GuiaEmpresarial.tsx` + produtizar os 4 pilares) → Tributário (começar pelas 6
calcs prometidas) → Ambiental (ligar backend pronto) → Licitações (decidir:
aposentar auditor keyword ou evoluir p/ leitor de edital com IA) → LGPD produto.

---

## Entregas desta rodada (mesmo branch)
- Verificador rigoroso de jurisprudência (DV do CNJ, súmulas por faixa,
  DataJud opt-in, score) — integrado à pipeline de peças. 217 testes verdes.
- Tema dourado + fundo branco da logomarca (AA verificado).
- Fix do atualizar-vps.sh (build do frontend).
