# Cutover 171: validação e retirada dos espelhos

Esta é uma orientação de homologação e continuidade. Não autoriza merge,
deploy, purga ou alteração de um banco real. A revisão humana permanece
vinculada ao SHA-256 do arquivo `171_preliminares_cutover.py`.

## Benchmark reproduzível

Use o Python/dependências do backend e um PostgreSQL 16 + pgvector **local de
teste**, com schema público migrado até 170 ou 171. O script aceita somente
loopback, nomes `ejc_test_*`, `ejc_higiene_*` ou `ejc_redundancias_*` e exige
`RUN_DB_TESTS=1`. DSNs com query string são recusados, pois opções libpq
podem sobrescrever host/banco. Variáveis `PGHOSTADDR`, `PGHOST`, `PGDATABASE`,
`PGPORT`, `PGSERVICE` e `PGSERVICEFILE` também são recusadas se preenchidas.
Configure `DATABASE_URL_SYNC` pelo mecanismo local seguro,
sem colocar a credencial na linha de comando ou no relatório.

```bash
cd backend
RUN_DB_TESTS=1 python scripts/benchmark_preliminares_cutover.py
# Carga ampliada, com os mesmos guards:
RUN_DB_TESTS=1 python scripts/benchmark_preliminares_cutover.py --sizes 10000,10000,50000
```

Cada origem recebe a quantidade escolhida de pais e documentos. A Sala
recebe dez mensagens e dois estados por pai, com conteúdo fictício de 1 KiB.
O script verifica contagens, equivalência de todos os campos projetados,
edição/exclusão, downgrade e reupgrade; confirma bloqueio de leitura e a
saída por `lock_timeout` sob concorrência. O relatório não inclui DSN,
conteúdo ou identificadores de clientes.

O schema descartável nasce vazio. Cargas e alterações são desfeitas por
rollback. Ao final, apenas as dez tabelas vazias criadas pelo próprio
benchmark são removidas, sem `CASCADE`; dados inesperados impedem a limpeza.
Nenhuma linha do schema público é consultada ou alterada.

`exclusive_during_upgrade_ms` mede da aquisição dos locks até o retorno de
`upgrade()`. Os locks continuam até a transação terminar; validações, probes
e downgrade do benchmark prolongam esse período. O número de relações inclui
as views criadas, além das dez tabelas. `lock_timeout=5s` limita a espera para
adquirir locks; não limita a duração do cutover depois da aquisição.

Medição local em 2026-10-03, com conteúdo de 1 KiB e migration SHA-256
`d83bbe64eae970796ae5334d6e0d249e343d12e674bda4910f53ab91c4c14890`:

| Registros canônicos | Tempo de upgrade | Locks exclusivos durante upgrade | Downgrade com verificação |
|---|---|---|---|
| 16.000 | 0,46 s | 0,45 s | 0,27 s |
| 160.000 | 3,66 s | 3,66 s | 1,99 s |
| 800.000 | 19,88 s | 19,88 s | 10,47 s |

Em todas as cargas houve equivalência de campos, rollback e reupgrade. O
leitor concorrente atingiu seu timeout de 200 ms; com outro leitor mantendo
lock, o cutover abortou em aproximadamente 5 s com SQLSTATE `55P03`, sem
alterar o schema. São medições locais, sem previsão de duração em produção.

## Homologação e aplicação

1. Revisar o arquivo exato, permissões e funções `SECURITY DEFINER`; registrar
   a aprovação humana no manifesto com o hash correspondente. Revisão de IA
   e testes não substituem essa decisão.
2. Atualizar a base, validar cadeia/head único e repetir o benchmark em
   homologação autorizada com volume, conteúdo e recursos representativos.
   Os tempos de uma máquina local não definem a janela de produção.
3. Verificar owners/grants, RLS e equivalência dos dados já existentes nas
   tabelas canônicas. RLS ou divergência de schema/dados aborta o cutover;
   reconciliar antes da janela, nunca relaxar os guards para fazê-lo passar.
   O executor deve ser confiável, sem compartilhamento/herança por consumidores
   SQL não confiáveis, e poder assumir os grantors originais para restaurar
   ACL delegada. Conservar esses papéis até a retirada do rollback.
4. Pelo procedimento de release: backup verificável e restauração testada,
   suspender escritores/consumidores antigos durante a janela e executar
   código/migration como uma mesma entrega. Falha de lock não deve iniciar
   tentativas ilimitadas. Validar leitura/escrita/conversão por origem e
   rollback em ambiente autorizado antes de concluir a promoção.

As funções de espelho têm `search_path=pg_catalog,pg_temp`, tipos/relações qualificados,
restrição de `TG_RELID` e nenhuma permissão avulsa de `EXECUTE` para os demais
papéis. Os seis espelhos são propriedade exclusiva do executor confiável;
owners/ACL originais, incluindo grantors e grants de coluna, são preservados
nos metadados de rollback. Triggers/regras legados incompatíveis abortam antes
do cutover. `TRUNCATE` é recusado nas quatro tabelas canônicas. O downgrade
confere os espelhos contra projeções fixas das tabelas canônicas, sem executar
definições de views alteráveis; divergência aborta antes de restaurar dados.
IDs e origem dos pais são imutáveis. Views mantêm projeção/ACL e
filtro de origem. A revisão deve considerar também privilégios efetivos por
herança de papéis e o comportamento real de quem lê/escreve essas views.

## Retirada futura: em duas entregas

**A. Estabilizar e encerrar consumidores antigos.** Manter as seis views,
quatro funções, oito triggers e seis tabelas `_legado_171` enquanto o rollback
171→170 estiver disponível. Monitorar falhas dos espelhos, tempo de escrita,
disco, conversão e leitura de cada origem. Inventariar SQL bruto, workers,
integrações e clientes externos das interfaces antigas. Sugestão de janela:
ao menos dois releases estáveis e 14 dias, ajustada à operação pelo titular.

Antes de avançar, comparar projeção canônica→espelho em ambos os sentidos sob
um snapshot consistente, incluindo todos os campos/IDs/documentos e
exclusões. Registrar que não há consumidores sem plano de atualização nem
incidentes de perda/isolamento pendentes. A ausência de referências no
repositório não prova ausência de consumidores externos.

**B. Retirar espelhos somente em nova migration aprovada.** Não editar a
171, nem executar remoção automática por idade. Preparar a entrega futura
com aprovação humana explícita, backup das tabelas/ACL, restauração ensaiada,
reconciliação de escritas após o backup e novo plano de recuperação. Avaliar
retirar primeiro o espelhamento e preservar as views enquanto existirem
consumidores; views e espelhos têm finalidades distintas.

Depois de remover os espelhos, o downgrade simples 171→170 deixa de ser uma
recuperação disponível: a entrega deve impedir sua execução isolada e
documentar como reconstruir os contratos antigos com dados atuais. Restaurar
um backup antigo sem reconciliar escritas posteriores perde dados. Purga
de dados, documentos e retenção LGPD exige decisão separada; não faz parte
da limpeza de caches/duplicações.
