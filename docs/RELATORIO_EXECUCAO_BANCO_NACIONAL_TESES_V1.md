# Relatório de Execução — Banco Nacional de Teses Jurídicas V1

**Projeto:** EJC + AcioneJus  
**Repositório:** `s2corporativo/EJC`  
**Branch local:** `feat/banco-teses-nacional-foundation`  
**Revisão auditada:** `8d4eaa11b47a36ca935e41de9906c1e74a986776`  
**Data:** 22 de agosto de 2026  
**Responsável técnico:** Manus AI

## 1. Resultado final direto

Foi executado o primeiro ciclo seguro da missão: auditoria estrutural do EJC e da superfície pública do AcioneJus; especificação do Banco Nacional de Teses; criação da camada canônica de fontes, snapshots, precedentes, teses, versões, relações, validações e lotes; exposição de API protegida; inclusão do módulo **Banco de Teses** no EJC; e criação da interface de pesquisa por pergunta/tema com separação entre ataque, defesa e ambos.

**Não foram criadas teses artificiais, não foram inventados precedentes e não houve coleta em massa.** Como não havia banco de produção acessível nem um repositório independente do AcioneJus disponível nesta sessão, a contagem real de registros alimentados permanece zero. A interface informa essa condição ao usuário e impede que registros não validados sejam apresentados como recomendação automática.

## 2. Entregas implementadas

| Entrega | Resultado verificado |
|---|---|
| Auditoria do EJC | Confirmada a coexistência do banco legado `teses`, jurisprudência interna, RAG, verificador de citações e matriz estruturada por caso. A camada nova não substitui essas estruturas. |
| Auditoria do AcioneJus | Confirmada a superfície pública de triagem/autoatendimento e a integração verificável existente no EJC. Não foi localizado repositório independente do AcioneJus na organização acessível. |
| Arquitetura | Documento completo em `docs/ARQUITETURA_BANCO_NACIONAL_TESES_V1.md`, com entidades, estados, pipeline, fontes, riscos, LGPD, supervisão humana e próximos lotes. |
| Persistência | Migração Alembic `147_banco_nacional_teses_foundation.py`, aditiva, encadeada após `146_case_sigilo_reforcado`. |
| ORM | `backend/app/models/legal_thesis_bank.py`, registrado no metadata em `backend/app/models/__init__.py`. |
| API | `backend/app/routers/banco_nacional_teses.py`, com rotas protegidas, deduplicação por hash/chave, validação de fonte e decisão humana. |
| Regras determinísticas | `backend/app/services/legal_thesis_bank_service.py`, com normalização de chave, SHA-256, vocabulário de estados e gate de recomendação. |
| Interface EJC | `frontend/src/pages/BancoNacionalTeses.tsx`, com busca por texto/tema, filtros por área e posição, cards, detalhe, força jurídica e aviso de fonte. |
| Navegação EJC | Novo módulo `/banco-de-teses` para equipe jurídica, integrado ao catálogo `Pesquisar & IA`. |
| Cliente frontend | `frontend/src/lib/legalThesisBank.ts`, com contratos tipados para listagem e detalhe. |
| Testes | Testes de domínio, idempotência, metadata, autenticação de rotas, UI e atualização dos guards de migração. |

## 3. Modelo canônico criado

A fundação separa explicitamente os conceitos que não podem ser confundidos: fonte, snapshot capturado, precedente, tese, estratégia, relação entre teses e índice futuro de RAG. As tabelas criadas são `legal_sources`, `legal_source_snapshots`, `legal_precedents`, `legal_theses`, `legal_thesis_versions`, `legal_thesis_precedents`, `legal_thesis_relations`, `legal_thesis_validation_events` e `legal_ingestion_runs`.

A tese possui os campos estruturais solicitados para identificação, tese principal, fundamento, raciocínio, pressupostos, fatos necessários, elementos a demonstrar, fatos impeditivos, exceções, fundamentação legal, estratégia, provas, documentos, argumento adversário, resposta e riscos. O campo `score_forca` é limitado a 0–100 e é acompanhado do aviso de que **força jurídica não é probabilidade matemática nem garantia de resultado**.

Os estados de publicação são controlados. Somente `validada` ou `revisada`, com registro de fonte validada e vigente, podem ser retornados pelo catálogo padrão. Precedente só é recomendável quando está `validado`, possui URL oficial, publicidade compatível e dados minimizados.

## 4. API criada

| Método | Rota | Função |
|---|---|---|
| `GET` | `/api/banco-nacional-teses/fontes` | Lista fontes cadastradas para equipe jurídica |
| `POST` | `/api/banco-nacional-teses/fontes` | Cadastra fonte, restrito a sócio/administrador |
| `POST` | `/api/banco-nacional-teses/fontes/{source_id}/snapshots` | Registra captura normalizada e hash idempotente |
| `POST` | `/api/banco-nacional-teses/precedentes` | Registra precedente associado a fonte e snapshot |
| `POST` | `/api/banco-nacional-teses/precedentes/{precedent_id}/decisao` | Valida, bloqueia, revisa ou marca precedente como superado |
| `GET` | `/api/banco-nacional-teses` | Lista teses validadas/revisadas com filtros |
| `POST` | `/api/banco-nacional-teses` | Cria tese em estado `coletada` |
| `GET` | `/api/banco-nacional-teses/{thesis_id}` | Consulta tese com precedentes vinculados |
| `POST` | `/api/banco-nacional-teses/{thesis_id}/validacoes` | Registra fonte ou precedente de suporte |
| `POST` | `/api/banco-nacional-teses/{thesis_id}/precedentes` | Vincula precedente favorável, contrário ou qualificado |
| `POST` | `/api/banco-nacional-teses/{thesis_id}/decisao` | Publica, revisa ou arquiva após gate humano |
| `POST` | `/api/banco-nacional-teses/lotes` | Abre checkpoint para lote futuro sem executar coleta automática |

Todas as rotas exigem `get_current_user`. A curadoria exige nível de advogado; aprovação/publicação exige sócio ou administrador. A API não possui rotina autônoma de raspagem nem publica conteúdo por inferência de IA.

## 5. Controle quantitativo real deste ciclo

| Indicador solicitado | Resultado deste ciclo | Observação de rastreabilidade |
|---|---:|---|
| Teses coletadas | **0** | Nenhum lote de dados foi executado |
| Teses validadas | **0** | Não havia registros para validação |
| Teses descartadas | **0** | Não houve lote processado |
| Áreas com schema/interface | **11** | Consumidor, Bancário, JEC, Civil, Trabalhista, Empresarial, Tributário, Administrativo/Licitações, Ambiental, Penal e Digital/LGPD |
| Áreas com evidência jurídica alimentada | **0** | A cobertura estrutural não deve ser confundida com cobertura documental |
| Precedentes cadastrados | **0** | Nenhum dado foi inserido sem fonte persistida |
| Processos analisados | **0** | Não foi classificado processo como vencedor |
| Duplicidades eliminadas | **0** | A idempotência por chave/hash foi implementada, mas não executada sobre lote |
| Teses em controvérsia | **0** | O grafo suporta relações contrárias/qualificadas; não houve carga |
| Módulos EJC integrados | **2** | API protegida e módulo frontend `/banco-de-teses` |
| Módulos AcioneJus integrados | **0** | Falta repositório/contrato privado acessível; integração foi especificada |

A meta de 3.000, 5.000 ou 10.000 teses não foi falsamente declarada como atingida. A quantidade somente deve crescer por lotes verificáveis, com fonte, snapshot, deduplicação, análise de contraposição, revisão e checkpoint.

## 6. Fontes consultadas e regras adotadas

Foram consultados o site público do AcioneJus, a documentação oficial do CNJ/DataJud, a Portaria CNJ nº 160/2020 em texto atualizado, o portal de dados abertos do STJ, o LexML, a LGPD e a Resolução CNJ nº 615/2025.

A Portaria CNJ nº 160/2020, com as alterações indicadas na fonte oficial, informa que a API pública/DataJud disponibiliza dados processuais em formato aberto, exclui ou anonimiza processos sob segredo de justiça, exige citação do CNJ/DataJud em produtos derivados e atribui ao consumidor a responsabilidade pelo uso dos dados [1] [2]. A Resolução CNJ nº 615/2025 exige curadoria de dados seguros, rastreáveis e auditáveis, proteção de dados, supervisão humana, explicabilidade, contestabilidade e monitoramento de riscos [3]. A LGPD exige finalidade, adequação, necessidade, transparência, segurança, prevenção e responsabilização no tratamento de dados pessoais [4].

Por consequência, DataJud não é tratado automaticamente como inteiro teor, resultado final ou prova de vitória. Estimativas internas do monitor CDC/JEC também não são convertidas em jurimetria nacional. O sistema não usa perfil pessoal especulativo de magistrado.

## 7. Validação executada

| Gate | Resultado |
|---|---|
| Compilação Python dos novos arquivos | Aprovada |
| Ruff nos arquivos modificados | Aprovado |
| Testes de fundação e rotas | **26 aprovados** |
| Testes dirigidos de tese, matriz, jurisprudência e verificador | **102 aprovados** |
| Suite backend completa | **5.866 aprovados, 273 ignorados, 34 warnings e 79 subtests** |
| Grafo Alembic e paridade de schema | **57 aprovados, 2 ignorados** |
| TypeScript frontend | Aprovado (`tsc --noEmit`) |
| Testes frontend completos | **107 arquivos e 569 testes aprovados** |
| Testes específicos da nova página | **2 aprovados** |
| Testes de catálogo/rotas frontend | **27 aprovados** |
| Build frontend | Aprovado; bundle `BancoNacionalTeses` gerado |
| ESLint somente nos arquivos novos/alterados | Aprovado |
| ESLint global do frontend | Bloqueado por três erros preexistentes em `components/DossieEstrategicoCaso.tsx`, linhas 201, 266 e 280; não pertencem ao módulo novo |
| `alembic heads`/histórico | Aprovado; head `147_banco_nacional_teses` único |
| Upgrade Alembic em banco real | Não executado: não havia PostgreSQL/Docker nem `DATABASE_URL_SYNC` disponível |
| `alembic upgrade --sql` da cadeia inteira | Bloqueado por falha preexistente na migration `032_indice_risco.py` (`TypeError: NoneType is not iterable`), antes de alcançar a migration 147 |

O lockfile frontend apresentou divergência anterior entre `package.json` e `pnpm-lock.yaml` para `globals`; a instalação temporária foi executada sem modo congelado apenas para validar o frontend, e a alteração do lockfile foi revertida. Nenhum segredo, banco de produção ou integração externa foi alterado.

## 8. Limites e próximos lotes recomendados

A próxima etapa tecnicamente segura é abrir o **Lote 01 — Consumidor/Bancário/JEC: fraude PIX, contratação não reconhecida e negativação indevida**, começando por legislação vigente, Súmulas/precedentes oficialmente confirmados e decisões públicas dos tribunais priorizados. Cada registro deverá ser inserido somente após a captura do documento, hash, URL oficial, checagem de publicidade, verificação de atualidade, identificação de posição contrária e revisão humana.

Depois do primeiro lote validado, a sequência recomendada é: **Lote 02 — Bancário/RMC e consignado; Lote 03 — Trabalhista/vínculo e pejotização; Lote 04 — Empresarial/desconsideração; Lote 05 — Tributário/executivo fiscal; Lote 06 — Administrativo/Licitações; Lote 07 — Ambiental; Lote 08 — Digital/LGPD; Lote 09 — Penal; Lote 10 — Civil geral**, com prioridade territorial posterior para TJMG, TRT3, TRF6, Betim, Contagem e Belo Horizonte, sempre que a fonte permitir granularidade objetiva.

## 9. Referências

[1]: https://datajud-wiki.cnj.jus.br/api-publica/ "CNJ/DataJud — API Pública"
[2]: https://atos.cnj.jus.br/atos/detalhar/3453 "CNJ — Portaria nº 160/2020 e alterações"
[3]: https://atos.cnj.jus.br/files/original1555302025031467d4517244566.pdf "CNJ — Resolução nº 615/2025"
[4]: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm "Planalto — Lei nº 13.709/2018, texto compilado"
[5]: https://dadosabertos.web.stj.jus.br/ "STJ — Portal de Dados Abertos"
[6]: https://www.lexml.gov.br/ "LexML Brasil — Rede de Informação Legislativa e Jurídica"
