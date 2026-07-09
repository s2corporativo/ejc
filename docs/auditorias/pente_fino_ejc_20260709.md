# Pente-fino técnico do EJC — auditoria estrutural inicial

Data: 09/07/2026  
Branch: `audit/pente-fino-20260709`  
Repositório: `s2corporativo/ejc`  
Escopo desta entrega: leitura direta dos arquivos críticos disponíveis pelo GitHub Contents API, criação de script de auditoria estática e consolidação dos achados prioritários.

## 1. Limitação operacional assumida

Esta auditoria foi feita sem clone local do repositório e sem execução de CI, porque o índice de busca de código do GitHub não estava disponível para o repositório e o ambiente de execução não possui acesso direto à internet/GitHub para `git clone`.

Por segurança, nenhuma exclusão de módulo e nenhuma alteração destrutiva foi feita nesta etapa. A intervenção aplicada foi não destrutiva: inclusão e ampliação de script de auditoria, correção do prompt jurídico central e relatório técnico para permitir validação local antes de alterações de produção.

## 2. Diagnóstico confirmado

### 2.1. Backend altamente acoplado no `main.py`

O arquivo `backend/app/main.py` importa e registra grande quantidade de routers diretamente. Esse padrão funciona, mas aumenta o risco de boot failure: qualquer erro de import em módulo secundário derruba toda a aplicação.

Risco: P1.

Recomendação:

1. Criar registro modular por grupos: core, jurídico, financeiro, IA, integrações, portal e experimental.
2. Colocar módulos beta/experimentais atrás de feature flags.
3. Manter apenas rotas core sempre obrigatórias no boot.
4. Criar teste de import mínimo: `python -c "from app.main import app; print(len(app.routes))"`.

### 2.2. Segurança/autenticação está melhor do que versões anteriores, mas exige revisão contínua

O `AuthMiddleware` está registrado e há lista explícita de prefixos públicos. Isso corrige a falha histórica de routers públicos, mas a lista pública precisa permanecer curta e auditada.

Risco atual: P1 se novos routers forem adicionados sem RBAC por rota.

Recomendação:

1. Todo router novo deve declarar explicitamente `Depends(get_current_user)` ou `require_roles`.
2. Rotas realmente públicas devem ter comentário de justificativa e validação alternativa, como token HMAC ou API key.
3. O script `scripts/ejc_static_audit.py` verifica routers de escrita sem dependência de autenticação claramente detectável.

### 2.3. Governança de produção está parcialmente madura

`config.py` já falha em produção se `SECRET_KEY`, `PII_ENCRYPTION_KEY`, `PII_HASH_KEY`, `FRONTEND_URL` e CORS estiverem inseguros. O `docker-compose.yml` prende backend/frontend/Ollama/Langfuse ao loopback ou rede interna, o que é correto para VPS.

Risco atual: P2.

Recomendação:

1. Não relaxar essas travas.
2. Não expor Postgres, Redis, Ollama ou Langfuse diretamente na internet.
3. Criar checklist obrigatório pré-deploy com backup, migration current/head e health/readiness.

### 2.4. Política de apresentação da IA foi ajustada

Foi removida do prompt central a linguagem que desqualificava a resposta como mero rascunho e impedia a IA de se apresentar em padrão jurídico forte. O arquivo `backend/app/services/legal_base.py` agora orienta a IA a apresentar respostas como advogado experiente: tese, fundamento, prova, risco, estratégia, providência prática e conclusão objetiva.

Ponto preservado: a IA continua proibida de inventar lei, súmula, jurisprudência, número de processo, documento, dado financeiro ou fato.

Pendências residuais detectadas:

1. `backend/app/routers/diplomacia_v3.py` ainda contém metadados antigos `is_rascunho` e `aviso_hitl`.
2. `frontend/src/pages/SalaDeGuerra.tsx` ainda contém componente visual com texto de rascunho obrigatório.
3. O script de auditoria foi ampliado para localizar esses resíduos como `stale_ai_policy_language`.

Observação: a tentativa de alterar `diplomacia_v3.py` diretamente foi bloqueada pela ferramenta de escrita, portanto o patch não foi aplicado e deve ser feito localmente ou em nova tentativa controlada.

### 2.5. Módulos inflados por ondas de IA

Foram confirmados nomes e camadas com sinais de escopo excessivo ou de baixa relação custo/benefício operacional.

Candidatos a manter apenas com feature flag ou migrar para legado:

| Módulo/área | Status recomendado | Motivo |
|---|---:|---|
| `diplomacia_v3` | Renomear/consolidar | A função de cálculo e negociação é útil, mas o nome deve virar algo objetivo, como `Acordos e Liquidez`. |
| `verse` | Ocultar/legado | Endpoint religioso sem aderência operacional ao núcleo jurídico. Se mantido, deve ser widget pessoal, não módulo sistêmico. |
| `sala_de_guerra_v3` | Consolidar | Há `sala_de_guerra` e `sala_de_guerra_v3`; manter uma versão canônica. |
| `data_room_v4` | Legado/alto risco | Declara modelo ORM dentro do router, em paralelo ao `data_room.py`, que é mais maduro. |
| `jurimetria_extra` | Consolidar | Evitar duplicidade com `jurimetria` e `analytics`. |
| `ia_extra`, `ia_especializada`, `ia_defensiva`, `ia_adversarial`, `ia_citacoes` | Consolidar sob AI Gateway | Excesso de routers de IA tende a gerar rotas duplicadas, políticas divergentes e manutenção cara. |
| `victory_vault` | Renomear ou absorver por Banco de Teses | A função é útil, mas o nome é promocional e o histórico de mock exige cuidado. |
| `radar-regulatorio`/`noticias`/`diario-oficial` | Manter opt-in | Alto custo de manutenção por dependência externa/scraping. |
| `visual_law` | Manter como camada de apresentação | Não deve virar dependência central de regra jurídica. |

### 2.6. Data Room duplicado

`backend/app/routers/data_room.py` é o caminho mais maduro: possui token externo, rate limit, expiração, limite de acessos, logs de IP/User-Agent e validação de confidencialidade/ownership dos documentos.

`backend/app/routers/data_room_v4.py` é tecnicamente inferior e mais arriscado porque:

1. declara `DataRoomSala(Base)` dentro do próprio router;
2. usa tabela própria `dataroom_salas`, separada da modelagem canônica;
3. tem superfície funcional menor;
4. cria duplicidade conceitual e risco de drift de migrations.

Recomendação: classificar `data_room_v4` como legado/oculto e migrar qualquer funcionalidade útil para `data_room.py`. Não remover sem confirmar se há tela ou consumo ativo.

### 2.7. Sala de Guerra duplicada

`backend/app/routers/sala_de_guerra.py` é o módulo de painel por caso, com dados de time, prazos, horas, checklists, documentos recentes, movimentos, teses e risco.

`backend/app/routers/sala_de_guerra_v3.py` traz sentinela, simulação adversarial e Visual Law PDF. A função é útil, mas deve ser absorvida pela Sala de Guerra canônica, não permanecer como módulo paralelo permanente.

Recomendação: manter uma rota canônica por caso e mover recursos extras para subrotas do módulo principal.

### 2.8. Victory Vault

O backend atual já não usa persistência puramente em memória: há serviço com PostgreSQL e seed mock apenas fora de produção. Porém, o módulo ainda conserva linguagem e histórico de demonstração.

Recomendação:

1. Renomear no menu para `Banco de Teses e Modelos`.
2. Manter `victory_vault` como alias técnico temporário, com depreciação futura.
3. Proibir seed mock em qualquer ambiente que use dados reais.
4. Exigir RBAC por perfil e auditoria em criação/edição/exclusão de teses/modelos.

### 2.9. Module Registry

O `module_registry.py` é uma boa base para governança modular. Porém, precisa deixar de ser apenas mapa descritivo e virar instrumento de saneamento: status `ativo`, `beta`, `legado`, `descontinuar`, `oculto`, com feature flag e rota/módulo dono.

Correção sugerida:

1. Acrescentar status operacional mais granular.
2. Corrigir prefixos divergentes, especialmente módulos cujo path real usa underscore e registry usa hífen.
3. Expor no frontend uma tela de saneamento: módulos sem endpoint, sem manual, beta, legado e com alta sensibilidade LGPD.

## 3. Correções aplicadas nesta branch

### 3.1. Script de pente-fino estático

Criado e ampliado:

`/scripts/ejc_static_audit.py`

Checks incluídos:

1. Conflitos de merge reais.
2. Possíveis segredos versionados.
3. Sintaxe Python via `ast.parse`.
4. Acoplamento excessivo de routers em `main.py`.
5. Routers de escrita sem autenticação/RBAC claramente detectável.
6. Modelos ORM declarados dentro de routers.
7. Routers versionados/paralelos como `*_v3`, `*_v4`, `*_extra`, `*_router`.
8. Divergências no `module_registry.py`.
9. Linguagem de mock/demo/hype em arquivos de runtime/documentação.
10. Resíduos da política antiga de IA, como `is_rascunho`, `aviso_hitl` e textos de rascunho obrigatório.

Comando:

```bash
python scripts/ejc_static_audit.py --root .
```

Saídas locais:

```text
audit_reports/ejc_static_audit.json
audit_reports/ejc_static_audit.md
```

Critério de saída:

```text
P0 -> exit 2
P1 -> exit 1
P2/P3 -> exit 0
```

### 3.2. Prompt jurídico central

Alterado:

`backend/app/services/legal_base.py`

Efeito:

1. Remove linguagem de bloqueio absoluto.
2. Orienta a IA a responder em padrão de advogado experiente.
3. Mantém vedação a invenção de fonte, fato, número de processo, documento ou dado financeiro.

## 4. Correções recomendadas para a próxima PR funcional

### P0 — bloquear antes de deploy

1. Rodar o script criado nesta branch.
2. Rodar:

```bash
git status
python scripts/ejc_static_audit.py --root .
cd backend && python -m compileall app
cd ../frontend && npm run build
```

3. Se houver P0, não fazer deploy.

### P1 — reduzir risco de queda do sistema

1. Modularizar registro de routers.
2. Consolidar duplicidades de versões: `*_v3`, `*_v4`, `*_extra`.
3. Padronizar RBAC backend para módulos financeiros, auditoria, dados sensíveis, IA e portal.
4. Criar testes mínimos de boot, health e rotas críticas.
5. Remover modelos ORM de dentro de routers.

### P2 — saneamento de produto

1. Ocultar módulos não essenciais do menu.
2. Renomear módulos com linguagem promocional.
3. Classificar módulos por valor real: essencial, útil, experimental, legado, remover.
4. Criar métrica de uso por módulo antes de excluir definitivamente.
5. Ajustar textos remanescentes da IA para padrão jurídico-profissional.

## 5. Módulos que devem ser núcleo permanente

Manter e estabilizar:

1. Autenticação, usuários, RBAC e auditoria.
2. Clientes e dossiê do cliente.
3. Casos/processos.
4. Prazos, suspensões, intimações e tarefas.
5. Documentos/GED/Data Room canônico.
6. Peças, modelos, banco de teses e validação jurídica.
7. Financeiro/honorários/despesas.
8. Portal do cliente.
9. AI Gateway/RAG com padrão profissional de advogado e trilha de auditoria.
10. DataJud/DJEN, desde que com controle de erro e opt-in.

## 6. Módulos que não recomendo manter como produto principal

Não recomendo manter em destaque, salvo prova de uso real:

1. `data_room_v4`.
2. `verse`.
3. nomes promocionais como `Victory Vault` no menu final.
4. versões paralelas `*_v3`, `*_v4`, `*_extra` sem owner técnico claro.
5. routers de IA fora do AI Gateway sem justificativa arquitetural.

## 7. Checklist de validação

- [ ] Backend importa `app.main` sem erro.
- [ ] `python scripts/ejc_static_audit.py --root .` executa.
- [ ] Nenhum P0 permanece.
- [ ] Frontend compila.
- [ ] `docker compose config` passa.
- [ ] `alembic current` e `alembic upgrade head` testados em ambiente de homologação.
- [ ] `/api/health` responde.
- [ ] `/api/health/ready` responde 200 com banco ativo.
- [ ] Rotas financeiras exigem perfil de gestão/financeiro.
- [ ] Rotas de IA mantêm sanitização de PII.
- [ ] Nenhum dado sensível aparece em log.
- [ ] Módulos beta/legados ficam ocultos ou sob feature flag.
- [ ] `data_room_v4` classificado como legado ou removido após confirmação de não uso.
- [ ] Resíduos `is_rascunho`/`aviso_hitl` removidos dos fluxos de apresentação jurídica.

## 8. Decisão técnica

O sistema não deve continuar crescendo por adição de módulos. O próximo ciclo correto é saneamento: cortar duplicidades, colocar módulos experimentais em feature flag, consolidar IA no gateway, endurecer RBAC, validar build e criar um mapa de módulos com status real.

A orientação é não remover nada em produção sem telemetria mínima de uso, backup e rollback. A remoção deve seguir: ocultar no menu -> desativar por flag -> monitorar 7 a 14 dias -> remover rota/backend/migration apenas se não houver dependência.
