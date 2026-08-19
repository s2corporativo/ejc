# Definition of Done — EJC

Esta política define o mínimo para uma alteração ser considerada pronta para promoção. Ela não substitui revisão jurídica humana, CI ou homologação; organiza esses controles em uma sequência única e auditável.

## Regra central

Uma frente segue o fluxo:

**Issue → diagnóstico → branch → implementação → testes → PR → CI → revisão → merge → deploy controlado → smoke/homologação → encerramento.**

Nenhum item é considerado concluído apenas porque o código foi escrito.

## Diagnóstico obrigatório antes da implementação

Registrar no PR ou Issue, quando aplicável:

- módulo e camada afetados;
- arquivos/contratos envolvidos;
- impacto técnico e dependências;
- impacto jurídico/LGPD;
- risco operacional;
- testes necessários;
- rollback.

## Backend

- [ ] inicia/compila sem erro;
- [ ] endpoint/serviço testado;
- [ ] autenticação, RBAC/ownership e menor privilégio preservados;
- [ ] regra de negócio permanece fora do router quando não trivial;
- [ ] validação Pydantic e erros sem stack trace/segredo/PII;
- [ ] auditoria registrada quando houver impacto jurídico, financeiro, documental, processual, cadastral ou de segurança.

## Frontend

- [ ] TypeScript e build passam;
- [ ] rota e papel permitido estão coerentes com o backend;
- [ ] loading, erro e vazio tratados;
- [ ] interação crítica possui feedback claro;
- [ ] nenhuma autorização depende apenas do frontend;
- [ ] fluxo não duplica tela/módulo canônico sem decisão arquitetural registrada.

## Banco e migrations

Quando houver migration:

- [ ] campo/tabela não existia;
- [ ] reserva de migration atualizada;
- [ ] `upgrade` testado;
- [ ] `downgrade` testado ou impossibilidade justificada;
- [ ] dado legado considerado;
- [ ] alteração destrutiva possui backup e rollback explícitos;
- [ ] sem drift entre modelos e schema esperado.

## Jurídico, prazos e IA

- [ ] fato extraído separado de inferência;
- [ ] fonte jurídica rastreável e, quando aplicável, oficial/vigente;
- [ ] revisão humana preservada em saída com efeito jurídico;
- [ ] mudança no núcleo jurídico de IA passou pelo gate de gold set humano quando acionado;
- [ ] prazo processual nunca é confirmado automaticamente quando cálculo/calendário estiver preliminar ou degradado;
- [ ] regime processual está explícito quando necessário.

## Segurança e LGPD

- [ ] nenhum segredo, `.env`, token ou credencial versionado;
- [ ] logs sem CPF/CNPJ/e-mail/segredo/conteúdo sensível desnecessário;
- [ ] mínimo privilégio e segregação de acesso mantidos;
- [ ] IDOR/ownership considerados em recursos de cliente/caso/documento/financeiro;
- [ ] indisponibilidade crítica falha de forma segura, sem converter erro em resultado válido;
- [ ] retenção/minimização de dados considerada quando houver novo dado pessoal.

## CI e promoção

Antes do merge:

- [ ] P0 Guard verde;
- [ ] CI principal verde no HEAD exato;
- [ ] Release Gate verde quando aplicável;
- [ ] migrations aplicam em banco efêmero quando houver banco;
- [ ] riscos residuais e rollback estão escritos.

Após merge/deploy:

- [ ] `/api/health` responde;
- [ ] `/api/health/ready` responde;
- [ ] smoke pós-deploy passa;
- [ ] fluxo crítico alterado foi homologado;
- [ ] nenhuma regressão relevante foi observada;
- [ ] Issue/PR antigo supersedido foi encerrado ou recebeu vínculo para a continuação.

## Regra de evidência

Checkbox sem evidência não substitui teste. Sempre que existir teste automatizado, o resultado do CI é a fonte principal. Itens humanos — validade jurídica, UX, revisão de conteúdo, decisão de risco — devem registrar quem revisou e o que foi conferido, sem expor dados sigilosos.

## Rollback mínimo

Toda alteração deve permitir retorno por `git revert` quando for apenas código. Se houver banco/configuração/dado, o PR deve indicar a reversão correspondente e as pré-condições de backup.