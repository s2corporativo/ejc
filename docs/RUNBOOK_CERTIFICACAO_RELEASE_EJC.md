# Runbook de certificação de release do EJC

**Versão:** 2026-08-05  
**Issues de origem:** #381, #407 e #411  
**Regra:** este runbook não autoriza produção por si só. A certificação só existe quando o pacote real de evidências passa no certificador e recebe as três aprovações obrigatórias.

## 1. Objetivo

Vincular, de forma rastreável, uma release específica do EJC aos seguintes controles:

- commit aprovado e commit efetivamente implantado;
- CI e gates de governança no mesmo SHA;
- H01–H15 sem falha ou bloqueio;
- proteção administrativa da `main`;
- backup cifrado e cópia externa;
- restauração real de banco e uploads em ambiente isolado;
- deploy e rollback comprovados;
- auditoria final de RBAC, IDOR, LGPD e IA/RAG;
- RPO/RTO formalmente aprovados;
- decisão expressa entre piloto controlado e produção;
- aprovação técnica, jurídica/LGPD e do titular do produto.

O script `qa/homologacao/certificar_release.py` apenas valida evidências já produzidas. Ele não acessa a VPS, não executa deploy, não cria backup e não recebe credenciais.

## 2. Restrições obrigatórias

1. Não usar banco, documentos ou clientes reais nos testes H01–H15.
2. Não registrar senha, código TOTP, cookie, JWT, chave de API, chave privada ou conteúdo de `.env` em arquivo, issue, log ou artefato.
3. Não executar migration antes de backup cifrado e confirmação de head Alembic único.
4. Não executar restauração sobre o banco de produção.
5. Não considerar job verde em branch diferente como evidência da release.
6. Não certificar se o SHA implantado divergir do SHA aprovado.
7. Não usar `git reset --hard`, `git clean -fd`, `DROP`, `TRUNCATE` ou alteração manual de produção como procedimento normal.
8. Qualquer evidência deve ser sanitizada e conter apenas resultado, horário, executor, SHA, hashes/tamanhos quando aplicável e referência ao artefato.

## 3. Fase 0 — congelar e selecionar a release candidata

Antes da homologação:

1. suspender merges paralelos que alterem migrations, autenticação, RBAC, documentos, Portal, backup ou IA/RAG;
2. reconciliar PRs abertos sobre a `main` atual;
3. resolver sobreposição de arquivos e colisões Alembic;
4. escolher um único SHA candidato;
5. registrar esse SHA como `approved_commit_sha` no manifesto;
6. executar todos os workflows no mesmo SHA.

Comandos de inspeção, sem alteração:

```bash
cd /opt/ejc
git status --short
git fetch --all --prune
git rev-parse HEAD
git log -1 --oneline
docker compose config >/dev/null
docker compose config --services
```

Se `git status --short` não estiver vazio, interromper. Não sobrescrever alteração local sem diagnóstico e cópia segura.

## 4. Fase 1 — proteção administrativa da `main`

Criar ou revisar o ruleset da branch `main` no GitHub com, no mínimo:

- pull request obrigatório;
- pelo menos uma aprovação humana;
- resolução obrigatória das conversas;
- bloqueio de force push;
- bloqueio de exclusão da branch;
- atualização da branch antes do merge;
- restrição de bypass administrativo;
- checks obrigatórios do CI, Release Gate, Continuity/UI, Architecture Inventory e contrato da certificação;
- merge somente após todos os checks no head exato.

A evidência deve mostrar as regras ativas, sem expor dados de conta além do necessário. Registrar a referência em `controls.branch_protection.evidence`.

## 5. Fase 2 — deploy controlado em homologação

Carregar configurações e credenciais somente pelo cofre/secret manager da infraestrutura. Não colar valores no terminal, no repositório ou no manifesto.

Procedimento mínimo:

```bash
cd /opt/ejc
git status --short
git fetch --all --prune
git checkout main
git pull --ff-only
export RELEASE_SHA="<SHA APROVADO>"
test "$(git rev-parse HEAD)" = "$RELEASE_SHA"
docker compose config >/dev/null
./scripts/backup.sh
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
docker logs ejc_backend --tail 100
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/health/ready
```

### Quando houver migration

Antes do upgrade:

```bash
./scripts/backup.sh
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
```

Interromper se houver mais de um head ou se o head não corresponder à cadeia aprovada. Somente então:

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
docker compose restart backend worker
docker logs ejc_backend --tail 100
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/health/ready
```

Registrar `deployed_commit_sha` com o valor de `git rev-parse HEAD` após o deploy. O certificador exige igualdade literal com `approved_commit_sha`.

## 6. Fase 3 — login real e 2FA

Executar H01 com contas de homologação e dados fictícios.

Verificar separadamente:

- login válido;
- senha inválida;
- sessão e refresh;
- logout/revogação;
- troca obrigatória de senha, quando aplicável;
- comportamento do kill switch temporário de 2FA;
- preservação dos segredos TOTP existentes;
- impossibilidade de cadastrar, substituir ou excluir TOTP enquanto o bypass estiver ativo;
- reativação controlada por configuração, sem alteração de banco.

Nunca registrar senha, TOTP, cookie ou token na evidência. Registrar apenas status HTTP, resultado esperado/observado, papel, duração e SHA.

## 7. Fase 4 — executar H01–H15

Primeiro validar o contrato sem rede:

```bash
python qa/homologacao/run_homologacao.py --validate
```

Depois, no ambiente de homologação, injetar as credenciais fictícias pelo mecanismo seguro da infraestrutura e executar:

```bash
python qa/homologacao/run_homologacao.py
```

O resultado esperado fica em:

```text
qa/homologacao/reports/homologacao_report.json
```

Regras de aceite:

- H01–H12 e H15 devem sair `PASS` no relatório automatizado;
- qualquer `FALHA` ou `BLOQUEADO` impede certificação;
- H13 e H14 podem ser substituídos por evidência manual porque exigem operação real de backup/restauração e deploy/rollback;
- override manual é proibido para qualquer outro cenário;
- os papéis obrigatórios devem incluir superadmin, admin, sócio, advogado, advogado auxiliar, secretaria, financeiro, estagiário e cliente externo, conforme o roteiro de homologação.

## 8. Fase 5 — H13: backup e restauração real

### 8.1 Backup

Com a credencial exclusiva de backup instalada fora do repositório:

1. executar o wrapper canônico de backup;
2. confirmar artefato cifrado do banco;
3. confirmar artefato cifrado dos uploads;
4. confirmar cópia externa/offsite;
5. registrar somente nome lógico, horário, hash e tamanho;
6. confirmar que nenhum dump ou upload permaneceu em claro fora da área temporária controlada.

### 8.2 Restauração

Em ambiente isolado e banco vazio:

1. baixar uma dupla de artefatos cifrados;
2. descriptografar com a chave custodiada pelo mecanismo seguro;
3. restaurar o banco vazio;
4. restaurar os uploads;
5. verificar integridade referencial e migrations;
6. iniciar a aplicação sobre a cópia restaurada;
7. efetuar login com conta fictícia;
8. consultar caso e documento fictícios;
9. medir o tempo total;
10. eliminar com segurança os artefatos temporários.

Não executar restauração sobre produção. Não registrar comandos contendo segredos.

Preencher no manifesto:

- `database_encrypted=true`;
- `uploads_encrypted=true`;
- `offsite_copy=true`;
- `database_restored=true`;
- `uploads_restored=true`;
- `application_started=true`.

## 9. Fase 6 — H14: rollback comprovado

O rollback deve ser testado em homologação usando a imagem e o schema compatíveis da release anterior.

Provar, no mínimo:

- identificação da imagem anterior;
- reversão do backend e frontend;
- compatibilidade do banco;
- procedimento de downgrade quando realmente necessário e aprovado;
- health e readiness após a reversão;
- login fictício e consulta básica;
- tempo total de recuperação;
- ausência de perda ou duplicação de dados da massa fictícia.

Se a migration for expand-only e compatível com a versão anterior, registrar essa decisão. Se exigir downgrade, testar o downgrade em cópia restaurada antes de qualquer uso operacional.

## 10. Fase 7 — auditoria final

A certificação exige evidência cumulativa de:

- RBAC por papel e negações explícitas;
- IDOR/ownership entre carteiras e Portal;
- LGPD: minimização, logs, publicação documental, retenção e anonimização;
- IA/RAG: isolamento por cliente/caso, fontes, vigência, HITL, citações e comportamento fail-closed;
- ausência de segredo em logs, respostas e artefatos;
- uploads, hash, integridade e controles de conteúdo conforme a release candidata.

Qualquer P0/P1 aberto precisa estar corrigido no SHA candidato ou formalmente aceito como restrição de piloto. Uma decisão de produção não admite restrições pendentes no manifesto.

## 11. Fase 8 — RPO e RTO

O manifesto exige valores positivos e aprovação formal.

Como ponto de partida para **piloto controlado**, pode-se avaliar:

- RPO de até 24 horas;
- RTO de até 4 horas.

Esses números são proposta inicial, não decisão automática. Devem ser comparados com a frequência real do backup e com o tempo medido de restauração. Para produção plena, definir os valores a partir dos testes reais, capacidade da infraestrutura e impacto jurídico/operacional de indisponibilidade.

Registrar a decisão em ata sanitizada e preencher `controls.rpo_rto` com `status=APPROVED`.

## 12. Fase 9 — manifesto e certificação

Copiar o modelo sem substituir o arquivo de exemplo:

```bash
cp qa/homologacao/release_manifest.example.json \
  qa/homologacao/reports/release_manifest.json
```

Preencher apenas referências sanitizadas. Não inserir anexos, documentos, credenciais ou dados pessoais no JSON.

Executar:

```bash
python qa/homologacao/certificar_release.py \
  --manifest qa/homologacao/reports/release_manifest.json \
  --report qa/homologacao/reports/homologacao_report.json \
  --output qa/homologacao/reports/release_certification.json
```

Resultados possíveis:

- `CERTIFICADO_PILOTO_CONTROLADO`;
- `CERTIFICADO_PRODUCAO`;
- `NAO_CERTIFICADO` com causa objetiva.

Também é possível disparar manualmente o workflow **EJC Release Certification**, informando os caminhos do manifesto e do relatório já presentes na branch controlada.

## 13. Aprovações e ata final

São obrigatórias três aprovações distintas:

1. responsável técnico;
2. responsável jurídico/LGPD;
3. titular do produto.

A ata final deve registrar:

- SHA aprovado e implantado;
- ambiente;
- resultado H01–H15;
- backup, restauração e rollback;
- RPO/RTO;
- riscos residuais;
- decisão entre piloto controlado e produção;
- restrições do piloto, quando houver;
- responsáveis e timestamps.

A ata não deve conter assinatura privada, credencial, token, dados de clientes ou documentos reais. A referência sanitizada da ata deve ser usada nas aprovações do manifesto.

## 14. Encerramento das issues

### Issue #381

Somente encerrar após H01–H15 `PASS`, backup/restauração, rollback e três aprovações.

### Issue #411

Somente encerrar após comprovação de deploy no SHA, login real, proteção da `main`, backup exclusivo, restauração, RPO/RTO, auditoria final e ata de piloto/produção.

### Issue #407

Não encerrar apenas com a certificação. Os itens estruturais devem estar implementados e testados no SHA candidato ou explicitamente permanecer como roadmap posterior ao piloto, sem serem apresentados como concluídos.

## 15. Rollback deste mecanismo de certificação

Esta entrega não altera banco, API, autenticação ou frontend. Para reverter:

```bash
git revert <commit-da-entrega-de-certificacao>
```

O revert remove o workflow, o certificador, os testes e este runbook. Evidências operacionais produzidas fora do repositório devem permanecer sob a política de retenção aprovada e não são apagadas por `git revert`.
