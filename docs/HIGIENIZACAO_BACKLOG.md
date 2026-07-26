# Backlog de Higienização — Backend

Catálogo de pendências mapeadas na passada de padronização/higienização do backend
(branch `chore/padronizacao-backend`, 2026-07-26). Itens listados aqui foram
**deliberadamente não resolvidos** nessa passada — ou por exigirem validação em
ambiente real (VPS), ou por não serem mecânicos/seguros.

## TODOs/FIXMEs no código

| Local | Marcador | Descrição |
|---|---|---|
| `backend/app/services/transparencia_service.py:218` | `TODO(verificar-vps)` | Confirmar o nome do parâmetro de filtro por CNPJ na API do Portal da Transparência (documentado como `cnpjSancionado`; algumas bases usam `cnpj`). Exige teste com a API real. |
| `backend/app/routers/car.py:34` | `TODO(verificar-vps)` | Confirmar o nome do parâmetro do imóvel esperado pela Infosimples na consulta SICAR/CAR (documentado como `car`; pode ser `numero_car`/`registro`). Exige teste com credencial real. |
| `backend/app/routers/evolution_webhook.py:47` | `TODO` | Mensagens recebidas via webhook Evolution (WhatsApp) são apenas logadas; integrar com fluxo de CRM/casos se necessário. Decisão de produto, não técnica. |

Obs.: ocorrências de "TODO"/"TODOS" em `visual_law_theme.py`, `system_prompts/`,
comentários e seeds são a palavra portuguesa ("todo documento", "todos os
prazos"), não marcadores de pendência.

## Padronizações não aplicadas (exigem decisão ou mudança de comportamento)

1. **Loggers `getLogger(__name__)` vs `getLogger("ejc.<modulo>")`** — o projeto
   convive com dois padrões (145 nomeados `ejc.*` vs 41 `__name__`). Nesta
   passada os loggers com nomes soltos fora de qualquer padrão (`war_room`,
   `skill_router`, etc.) foram alinhados ao namespace `ejc.*` dominante.
   Unificar os 41 `__name__` restantes é possível, mas muda o campo `logger`
   de muitos registros de log — avaliar impacto em dashboards/filtros antes.
   (`rag_juridico.py` ficou de fora por estar em manutenção paralela.)
2. **`transparencia_service.validar_cnpj`** — homônima da canônica de
   `validators_service`, mas com contrato diferente (normaliza para 14 dígitos
   e levanta `ValueError`; **não** valida dígito verificador). Não é duplicata
   consolidável sem mudar comportamento; considerar renomear para
   `normalizar_cnpj` para eliminar a ambiguidade.
3. **Schemas Pydantic inline em routers** — muitos routers definem schemas
   localmente em vez de `app/schemas/`. Migração é mecânica porém extensa;
   fazer por módulo, junto de mudanças funcionais de cada área.

## Itens verificados e considerados OK (não são dívida)

- `print(` só existe em `app/eval/` e `app/seeds/` — são scripts CLI executados
  fora do servidor; saída em stdout é o comportamento correto ali.
- Mensagens de `HTTPException(detail=...)` já estão todas em português.
- Nenhum `.pyc`/`__pycache__`/artefato versionado por engano.
- Nenhum `pdb.set_trace()`/`breakpoint()` em `app/` ou `tests/`.
- `ruff check app` e `ruff check tests` 100% limpos após esta passada.
