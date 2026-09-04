# Relatório — FASE 4 (execução parcial): Bloco 4C — Segurança/LGPD do Dossiê

**Data:** 2026-06-29 · **Escopo:** o plano da Fase 4 manda fechar os buracos de LGPD do bloco dossiê **antes** de qualquer unificação. Feito isso (alto valor, verificável). As fusões de namespace (cosméticas, exigem coordenação com frontend + validação em produção) ficam para quando o deploy estiver disponível.
**Regra:** nada executado contra banco; verificado por testes + boot + py_compile.

---

## O que foi corrigido (achados do plano, bloco 4C)

| # | Achado | Correção | Arquivo |
|---|--------|----------|---------|
| A2 | `GET /clients/{id}/dossie` entregava **CPF/CNPJ + casos + honorários** de qualquer cliente com apenas `get_current_user` (sem gate forte) | Aplicado o **mesmo gate** já usado no relatório financeiro do cliente (`_req_fin_adv` = superadmin/admin/socio/financeiro/advogado) — fonte única, sem inventar política | `routers/dossie_cliente.py` |
| B1 (IDOR) | `POST /cases/{id}/analisar` sem checagem de ownership (qualquer um analisava qualquer caso) | + `verificar_acesso_caso` (gate canônico) | `routers/cases.py` |
| B1 (LGPD) | `analise_estrategica.analisar_caso` chamava `sanitizar_pii` **sem `nomes_proteger`** e **sem a 2ª barreira** → nomes (parte contrária/cliente) e PII residual podiam ir ao Groq | + `nomes_proteger` (parte contrária + cliente, montados no caller) e **`validar_sem_pii` como segunda barreira fail-closed** (aborta antes do LLM se sobrar CPF/CNPJ/processo/e-mail) | `services/analise_estrategica.py` + `routers/cases.py` |

## Verificação
- ✅ `py_compile` OK; app sobe (453 rotas).
- ✅ **65 testes passando**, incluindo `test_analise_estrategica.py` (novo) que **prova** que CPF, nº de processo e nome do cliente são mascarados no prompt enviado ao LLM (monkeypatch do gateway).

## Bloco 4B/namespace — aliases canônicos `/api` (2026-06-29)

A pedido do usuário, executada a **parte segura da fusão de namespace** (estratégia de aliases, zero quebra). Os routers que estavam **só** sob `/api/v1` (prefixo único → sem colisão) ganharam o caminho **canônico `/api/*`**, mantendo `/api/v1/*` ativo como alias legado:

| Router | Legado (mantido) | Canônico (novo) |
|---|---|---|
| `relatorio` | `/api/v1/relatorio` | `/api/relatorio` |
| `exito_rateio` | `/api/v1/honorarios-exito` | `/api/honorarios-exito` |
| `financeiro_consolidado` | `/api/v1/financeiro` | `/api/financeiro` |
| `bank_analysis` | `/api/v1/bank-analysis` | `/api/bank-analysis` |
| `ai_tools` | `/api/v1/ai` | `/api/ai` (status, executar) |

`main.py` — 5 `include_router(..., prefix=API)` adicionados. Verificado: 465 rotas (+12), **0 colisões (método+path)**, 65 testes verdes. O frontend não muda (segue usando `/api/v1`); os canônicos ficam prontos para migração futura. **`ai_tools` foi normalizado** após verificar que `/ai/status` e `/ai/executar` NÃO colidem com as 19 rotas já existentes em `/api/ai`. Com isso a **normalização de namespace está completa** (sem outliers `/api/v1` por consolidar).

## O que NÃO foi feito (deliberadamente — fica para quando deployável)
- **Fusão de namespace/routers** (IA 7→2, honorários 4→1 sob `/api/honorarios`, dossiê) via **aliases deprecados**: é mudança que toca prefixos consumidos por ~13 telas do frontend e o ideal é validar em produção (deploy pausado). Cosmético/organizacional, não fecha risco — por isso adiado.
- **Padronização do motor de IA** (Groq direto → `ai_gateway` único): exige **teste de paridade** com o LLM real (não dá pra validar neste sandbox). Adiado.
- **Risco latente de shadowing** `ai.py`×`ia_extra.py` (mesmo prefixo `/api/ai`): hoje **sem colisão real** (laudo: zero shadowing); documentado para vigiar ao adicionar rotas.

## Próximas fases
- Restante da Fase 4 (consolidação de namespace + motor) → executar **após** deploy validado, com aliases e teste de paridade.
- Deploy das Fases 1–4 quando o ambiente permitir (Claude no PC do usuário ou dev).
