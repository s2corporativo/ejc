# RELATÓRIO ETAPA 6C — VERIFICAÇÃO PRÉ-DROP (autorização recebida, execução BLOQUEADA por evidência)

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`
Contexto: o usuário autorizou explicitamente o bloco destrutivo H1/H2 (com backup). Antes de qualquer DDL irreversível, rodei a trava obrigatória de due diligence — verificar se as colunas ditas "legadas" ainda são usadas pelo código. **Resultado: são código vivo. Nenhum DROP foi executado.**

## Princípio aplicado

Autorização permite executar; **não** permite quebrar a produção. A regra é: antes de uma ação irreversível, confirmar que a evidência sustenta *aquela* ação. A evidência (grep no código real) **não sustenta** os drops — ao contrário, prova que quebrariam funcionalidade. Surdez a isso, mesmo com "autorizo", seria negligência. Nenhuma alteração destrutiva foi feita.

## H1 — DROP das colunas legadas de `cases` (numero_processo, tribunal, comarca, vara, valor_causa) → **NÃO EXECUTADO**

As colunas são **ativamente usadas** em ~10 arquivos do backend, incluindo:
- `routers/cases.py:83` — busca filtra por `Case.numero_processo`.
- `routers/cases.py:270-282` — **write-through ativo**: quando `numero_processo` muda no caso, o código sincroniza para `processes` (INSERT/UPDATE do processo principal). Ou seja, `cases.numero_processo` ainda é alvo de escrita primária.
- `routers/cases.py:501,529,684,845`, `routers/clients.py:467`, `routers/datajud.py:43-84`, `routers/documents.py:90-98`, `routers/export.py:65`, `routers/conversao_caso.py:48-71` — leituras (DataJud, geração de documento, export, conversão de caso).
- `core/sql_safe.py:23` — whitelist de colunas.

**Consequência do DROP:** quebraria busca de casos, edição de caso, sincronização DataJud, geração de peça, export e conversão de caso. Inaceitável.

**Achado colateral importante:** o write-through de `cases.py:270` + a leitura via `processo_service.numero_processo_efetivo()` significam que **o risco central do M8 (campos legados divergindo) já está mitigado no código**. Não há, portanto, correção segura pendente para o M8 — o estado atual é funcionalmente consistente. Confirma a recomendação original da Etapa 6 (opção 3: não mexer).

## H2 — DROP de `cases.linked_judicial_case_id` → **NÃO EXECUTADO**

Menos usado que H1, mas **ainda vivo no frontend**:
- `frontend/src/pages/CasoDetalhe.tsx:572,584,587` — renderização condicional e navegação para o caso judicial vinculado (`navigate('/casos/{linked_judicial_case_id}')`).
- `frontend/src/types/index.ts:69` — tipo TypeScript do Case.
- `backend/app/schemas/case.py:85` — campo exposto na API.
- `backend/app/models/case.py:76` — coluna mapeada.

**Consequência do DROP:** a API pararia de devolver o campo → o bloco de UI "processo judicial vinculado" no `CasoDetalhe` sumiria silenciosamente, e o ORM SELECT quebraria enquanto o model ainda mapear a coluna. Seria uma remoção coordenada (model + schema + frontend + migration) de baixo valor, sobre um banco de produção que não posso testar localmente. Desproporcional.

## Decisão

**Nenhum DROP executado. Nenhuma migration destrutiva criada. Banco de produção intocado.** A autorização foi dada de boa-fé sob a premissa de que eram colunas órfãs; a verificação prova que não são. Mantenho as colunas.

## O que fica como recomendação (não urgente, não destrutivo)

- **M8:** nada a fazer — já mitigado em código (write-through + read-through). Aceitar como estado consistente e documentado.
- **`linked_judicial_case_id`:** se um dia for realmente aposentado, exige um bloco coordenado (remover do frontend `CasoDetalhe`/types → do schema → do model → só então DROP COLUMN, com backup e teste em cópia). Baixa prioridade; sem ganho funcional.

## Critério de aceite

- Due diligence executada antes de qualquer DDL: **ATENDIDO**.
- Nenhuma alteração destrutiva / dados preservados: **ATENDIDO**.
- Decisão fundamentada em evidência de código real e registrada: **ATENDIDO**.
