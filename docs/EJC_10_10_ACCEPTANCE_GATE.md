# EJC 10/10 — Critérios objetivos de certificação

**Status atual:** NÃO CERTIFICADO 10/10  
**Data-base:** 19/07/2026  
**Regra:** o EJC somente pode receber a classificação 10/10 quando todos os gates abaixo estiverem comprovados por evidência automatizada e homologação operacional.

## 1. Princípio de certificação

A classificação 10/10 não decorre da quantidade de módulos. Ela exige, cumulativamente:

1. correção funcional;
2. segurança e segregação de dados;
3. aderência jurídica e auditabilidade;
4. arquitetura coerente, sem duplicidades operacionais;
5. experiência de uso simples e contínua;
6. IA controlada, verificável e submetida a revisão humana;
7. banco e migrations íntegros;
8. observabilidade e recuperação de falhas;
9. CI/CD bloqueante e rastreável;
10. operação documentada e homologada por usuários reais.

## 2. Situação verificada na data-base

### Integrado na `main`

- Onda 1 da refatoração arquitetural: API canônica `/api/v1`, aliases de compatibilidade, contratos de domínio, normalização de rotas e inventário arquitetural.
- Hardening do núcleo de IA/RAG, incluindo resolução fail-closed, escopo de conhecimento e proteção de marcadores estruturais do AILog.
- Feed cognitivo DataJud e governança da base de conhecimento.

### Não integrado

As seguintes ondas foram encerradas sem merge e precisam ser reaplicadas sobre a `main` atual, com revalidação integral:

- Onda 2 — domínio canônico de Processos;
- Onda 3 — consolidação de Data Room e Teses v4;
- Onda 4 — Sala de Guerra canônica por caso;
- Onda 5 — timeline única e saúde operacional do caso;
- Onda 6 — painel contextual de saúde/timeline no frontend;
- Onda 7 — saúde operacional da carteira no Dashboard.

### Riscos residuais já identificados

- escopo e titularidade de eventos pessoais da agenda;
- possibilidade de atribuição de evento a terceiro e exposição indevida no oráculo de conflito;
- validação de pertencimento do comprovante de protocolo ao caso;
- ausência de testes completos de titularidade de procurações e IDOR de agenda;
- 2FA obrigatório por papel ainda sem enforcement duro;
- necessidade de comprovar a `main` consolidada em CI verde após merges sucessivos.

## 3. Gates obrigatórios

### G0 — Governança de merge e release

- [ ] branch `main` protegida;
- [ ] PR obrigatório para qualquer alteração;
- [ ] aprovação obrigatória de todos os checks do workflow `CI`;
- [ ] aprovação obrigatória do workflow `EJC Release Gate`;
- [ ] branch desatualizada impedida de merge;
- [ ] conversa/revisão não resolvida impedida de merge;
- [ ] merge direto na `main` bloqueado;
- [ ] deploy condicionado ao commit homologado.

### G1 — Backend e banco

- [ ] instalação limpa de `requirements.txt`;
- [ ] lint Ruff sem falhas;
- [ ] suíte backend integral com PostgreSQL 16 + pgvector real;
- [ ] zero falha e zero teste crítico ignorado;
- [ ] Alembic com head único;
- [ ] `upgrade head` validado a partir de banco vazio e cópia anonimizada;
- [ ] rollback documentado e testado para a release;
- [ ] ausência de colisões novas de método + rota;
- [ ] ausência de SQL de negócio indevido em routers.

### G2 — Frontend

- [ ] Prettier sem divergências;
- [ ] Vitest integral verde;
- [ ] TypeScript sem erros;
- [ ] build Vite verde;
- [ ] rotas canônicas e aliases legados testados;
- [ ] ausência de telas, botões e fluxos mortos;
- [ ] tratamento consistente de loading, vazio, erro e retry;
- [ ] acessibilidade mínima WCAG AA nos fluxos principais.

### G3 — Segurança, sigilo e LGPD

- [ ] zero achado crítico ou alto em auditoria;
- [ ] ownership aplicado antes de qualquer leitura ou mutação por caso/cliente;
- [ ] testes negativos de IDOR em todos os módulos sensíveis;
- [ ] segregação entre carteiras comprovada para todos os papéis;
- [ ] 2FA efetivamente obrigatório para papéis definidos;
- [ ] segredos exclusivamente no cofre/ambiente, nunca no repositório;
- [ ] auditoria de dependências Python e Node sem vulnerabilidade alta/crítica;
- [ ] trilha de auditoria imutável para ações jurídicas e de IA;
- [ ] retenção, descarte e exportação de dados pessoais documentados.

### G4 — IA jurídica e RAG

- [ ] fail-closed sem provedor elegível;
- [ ] pseudonimização antes de provedores externos;
- [ ] escopo RAG por cliente/caso comprovado por testes de isolamento;
- [ ] citações jurídicas verificáveis, com fonte, tribunal, data e vigência;
- [ ] gold sets por área do Direito e por tipo de tarefa;
- [ ] avaliação mínima definida para precisão, completude e alucinação;
- [ ] HITL obrigatório antes de aplicar, protocolar ou comunicar conteúdo;
- [ ] custo, modelo, prompt sanitizado, resposta e decisão humana auditados;
- [ ] indisponibilidade de IA não interrompe cadastro, prazos ou operação básica.

### G5 — Fluxos jurídicos ponta a ponta

Devem existir testes automatizados e homologação humana, no mínimo, para:

- [ ] documento → extração → novo caso → revisão → confirmação;
- [ ] cadastro manual simples de caso;
- [ ] cliente → atendimento → documentos pendentes → retorno;
- [ ] caso → processo principal/acessório → movimentação;
- [ ] intimação → prazo → tarefa → agenda → conclusão;
- [ ] documento/prova → estratégia → tese → peça → revisão;
- [ ] audiência → roteiro → ata → providências;
- [ ] honorários → parcelas → pagamento → conciliação;
- [ ] Raio-X avulso → análise → conversão em caso;
- [ ] DataJud → atualização → impacto cognitivo controlado;
- [ ] portal do cliente com segregação e trilha;
- [ ] backup → restauração → retomada operacional.

### G6 — Arquitetura e simplificação

- [ ] Caso como workspace central;
- [ ] separação inequívoca entre Caso e Processo;
- [ ] uma única fonte de verdade por entidade;
- [ ] módulos versionados legados apenas como adaptadores temporários;
- [ ] ausência de dupla escrita não controlada;
- [ ] aliases com telemetria, prazo de retirada e rollback;
- [ ] menus e rotas sem redundância operacional;
- [ ] nenhuma exclusão física antes de backfill, telemetria e validação.

### G7 — Observabilidade e continuidade

- [ ] health checks de aplicação, banco, filas, scheduler, IA e integrações;
- [ ] logs estruturados com correlação por requisição/caso;
- [ ] alertas para falha de jobs, prazos, backups, integrações e IA;
- [ ] métricas de erro, latência, fila, custo de IA e disponibilidade;
- [ ] backup automatizado, criptografado e com teste periódico de restauração;
- [ ] plano de recuperação com RPO/RTO definidos;
- [ ] rollback de deploy testado.

### G8 — Operação e usabilidade

- [ ] modo simples validado por advogado não técnico;
- [ ] modo avançado sem duplicar módulos;
- [ ] dashboard orientado a risco, prazo, pendência e próxima ação;
- [ ] saúde operacional por caso e carteira;
- [ ] timeline única e confiável;
- [ ] ajuda contextual e manual vivo por módulo;
- [ ] tempo de execução aceitável nos fluxos críticos;
- [ ] zero bloqueador em homologação real do escritório.

## 4. Critério final de aprovação

O EJC será certificado 10/10 somente quando:

- todos os itens G0 a G8 estiverem concluídos;
- CI e Release Gate estiverem verdes no commit exato da release;
- não houver issue P0/P1 aberta sem aceite formal de risco;
- os fluxos ponta a ponta tiverem evidência automatizada e ata de homologação;
- a release tiver rollback e restauração testados;
- o responsável técnico e o titular do produto aprovarem o checklist final.

## 5. Ordem de execução

1. endurecer governança de merge e checks obrigatórios;
2. fechar riscos residuais de segurança e titularidade;
3. reaplicar as Ondas 2 a 7 sobre a `main` atual, uma por vez;
4. executar testes completos, migrations e auditoria de segurança;
5. homologar os fluxos jurídicos ponta a ponta;
6. testar backup, restauração, deploy e rollback;
7. emitir a certificação interna da release.
