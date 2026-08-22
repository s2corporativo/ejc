# Banco Nacional de Teses Jurídicas — Auditoria e Arquitetura V1

**Projeto:** EJC + AcioneJus  
**Revisão de código auditada:** `8d4eaa11b47a36ca935e41de9906c1e74a986776`  
**Data da auditoria:** 22 de agosto de 2026  
**Escopo deste ciclo:** auditoria estrutural, arquitetura de governança e fundação persistente. Não houve coleta em massa nem publicação automática de tese não validada.

## 1. Resultado executivo

O EJC já possui uma base jurídica relevante, mas distribuída em camadas com finalidades diferentes. Há um banco legado de teses (`teses`), um repositório interno de jurisprudência (`jurisprudencias_internas`), uma base RAG com documentos e embeddings (`knowledge_docs`/`knowledge_chunks`), um verificador de citações e uma matriz estruturada por caso (`legal_issues`, `thesis_candidates`, `authority_records` e `evidence_links`). O sistema já aplica RBAC, escopo por caso/cliente, registro de uso de IA e aprovação humana para candidatos da matriz.

A lacuna principal não é ausência de qualquer banco de teses; é a falta de uma **camada nacional canônica, normalizada e versionada**, que separe fonte, documento capturado, precedente, tese, contratese, relação entre teses, validação e índice semântico. A arquitetura V1 preserva as tabelas existentes e adiciona somente a fundação necessária para impedir que texto de RAG ou saída de IA seja tratado como precedente validado.

> Regra operacional da V1: **nenhuma tese entra como recomendada automaticamente sem fonte rastreável, status de validação e revisão humana compatível com o risco.**

## 2. Auditoria da estrutura atual

| Componente | Situação verificada | Capacidade aproveitável | Lacuna para o banco nacional |
|---|---|---|---|
| EJC backend | FastAPI, SQLAlchemy assíncrono e Alembic, com 146 migrações versionadas | Integração natural por novos modelos e migração aditiva | A migração local do ambiente não pôde ser executada nesta máquina porque o binário `alembic` não está instalado |
| Banco legado de teses | Tabela `teses`, CRUD, ranking por taxa interna e vínculo com casos | Histórico do escritório e compatibilidade com telas existentes | Campos textuais, sem fonte normalizada, versão editorial, taxonomia completa, posição processual ou contratese estruturada |
| Jurisprudência interna | Tabela `jurisprudencias_internas`, busca externa LexML/TJMG e importação com deduplicação por número/tribunal | Repositório interno e conectores de pesquisa já existentes | Um único registro mistura identificação, ementa, fonte e classificação; não há entidade nacional de precedente com snapshots e validação independente |
| RAG | `knowledge_docs` e `knowledge_chunks` com pgvector, versionamento do documento, escopo e revisão manual | Busca semântica e separação pública/escritório/caso | RAG deve permanecer índice de recuperação; não pode ser a autoridade de origem nem substituir o registro jurídico normalizado |
| Verificação | Verificador estruturado de CNJ, recursos, súmulas, artigos e menções genéricas, com estados `verificada`, `identificada`, `suspeita`, `generica` e `possivelmente_desatualizada` | Gate anti-alucinação e conferência local/DataJud opt-in | O resultado precisa ser persistido como evento de validação ligado à fonte e ao precedente, com histórico de mudanças |
| Matriz de teses por caso | Questões, candidatos, autoridades e vínculos entre fato/prova/tese, com score determinístico e HITL | Detector de questões, provas e precedentes no contexto do caso | É uma camada de trabalho por caso, não um catálogo nacional reutilizável e versionado |
| IA e peças | Chamadas via gateway, sanitização de PII, AILog e avisos de revisão | Reuso do fluxo de rascunho e do citation gate | A recuperação futura deve aceitar apenas registros públicos e validados conforme filtros de status e escopo |
| AcioneJus público | Site público com triagem gratuita, autoatendimento documental, foco no JEC e causas de consumo; o site declara que não presta advocacia | Ponto de entrada de fatos/documentos e linguagem simplificada ao consumidor | Não há, no repositório acessível, uma aplicação AcioneJus separada com o banco nacional; a integração verificável hoje está no EJC, especialmente no fluxo `jec_triagem_minuta` e no monitor CDC/JEC |
| Monitor AcioneJus no EJC | Base de referência interna com padrões estimados, explicitamente rotulada como não oficial | Triagem e organização de intake | Estimativas internas não podem alimentar jurimetria nacional nem ser apresentadas como casos vencedores ou dados SENACON |

### 2.1 Limite de escopo constatado

Não foi localizado um repositório independente do AcioneJus na organização GitHub acessível. O domínio público foi consultado apenas para confirmar a superfície de entrada e o posicionamento do produto. Portanto, este ciclo implementa a fundação no EJC e deixa a integração do frontend privado do AcioneJus dependente do contrato de API e do repositório correspondente.

## 3. Princípios de arquitetura

A arquitetura adota seis separações obrigatórias. **Fonte** identifica quem publicou ou disponibilizou o dado. **Snapshot** preserva a versão capturada e seu hash. **Precedente** normaliza metadados do julgado sem apagar a origem. **Tese** registra a proposição argumentativa e seus pressupostos. **Estratégia** documenta quando usar, quando não usar, prova e resposta adversária. **RAG** é somente uma projeção pesquisável dessas entidades e dos documentos, nunca a fonte primária.

O banco não utilizará “taxa de sucesso” de decisões públicas como probabilidade de vitória. O campo de força jurídica será um score explicável e determinístico, sempre acompanhado de volume, período, cobertura, decisões contrárias e aviso de que **força argumentativa não equivale a garantia de resultado**.

A coleta deve aceitar documentos públicos e autorizados, respeitando termos de uso, segredo de justiça, anonimização e minimização. O DataJud disponibiliza metadados processuais e resguarda processos sigilosos e dados das partes conforme sua documentação oficial [1]. A Portaria CNJ nº 160/2020, atualmente alterada pela Portaria nº 374/2026, exige citação do CNJ/DataJud em produtos derivados, proíbe exploração comercial dos dados da API e ressalva que a precisão e atualidade dependem das remessas dos tribunais [2].

## 4. Modelo canônico V1

| Entidade | Finalidade | Regra de publicação |
|---|---|---|
| `legal_sources` | Cadastro de fonte primária, complementar e URL de validação | Fonte oficial ou autorizada explicitamente identificada |
| `legal_source_snapshots` | Versão capturada, hash, título, conteúdo normalizado e metadados | Nunca sobrescrever silenciosamente; nova captura gera snapshot |
| `legal_precedents` | Precedente/julgado normalizado, com tribunal, órgão, processo, datas, resultado e força | `validado` exige origem e URL/identificador rastreável |
| `legal_theses` | Tese nacional estruturada, posição ataque/defesa/ambos, taxonomia, pressupostos e estratégia | Somente `validada` ou `revisada` pode alimentar recomendação automática |
| `legal_thesis_precedents` | Relação tese–precedente, favorável/contrária/qualificada e trecho relevante | Relação sem precedente validado permanece não recomendável |
| `legal_thesis_versions` | Histórico imutável de cada versão da tese | Toda alteração material cria nova versão e motivo |
| `legal_thesis_relations` | Grafo de dependência, contradição, complemento, distinção e superação | Relações apontam para IDs canônicos, sem texto solto como chave |
| `legal_thesis_validation_events` | Auditoria de coleta, validação, revisão, descarte e superação | Evento humano registra usuário, papel, data e justificativa |
| `legal_ingestion_runs` | Checkpoint por lote/fonte, contagem, status e erro | Permite retomada idempotente e impede loop de coleta |

### 4.1 Campos mínimos da tese canônica

A tabela canônica terá identificação, área, subárea, instituto, tema, subtema, situação fática, tipo material/processual/probatório/subsidiário/redução, classificação ataque/defesa/ambos, parte favorecida, procedimento, instância, tese principal, fundamento resumido, raciocínio, pressupostos, fatos necessários, elementos a demonstrar, fatos impeditivos, exceções, estratégia, riscos, provas, documentos, argumento adversário e resposta.

A fundamentação legal será armazenada separadamente dos precedentes e da estratégia. Cada referência legal deverá possuir diploma, artigo e estado de verificação; o texto integral da norma não será substituído por uma paráfrase de IA. A taxonomia inicial será compatível com a prioridade declarada: Consumidor, Bancário, JEC, Civil, Trabalhista, Empresarial, Tributário, Administrativo/Licitações, Ambiental, Penal e Digital/LGPD.

## 5. Estados e gates

| Camada | Estados principais | Gate de saída |
|---|---|---|
| Ingestão | `coletada`, `em_processamento`, `validada`, `parcial`, `erro` | Item tem fonte, chave de origem e hash |
| Precedente | `nao_validado`, `identificado`, `validado`, `superado`, `revisar` | `validado` exige fonte oficial/autorizada e metadados mínimos |
| Tese | `coletada`, `em_analise`, `parcialmente_validada`, `validada`, `revisada`, `desatualizada`, `superada`, `arquivada` | Automação somente para `validada` ou `revisada` |
| Relação tese–precedente | `favoravel`, `contraria`, `qualificada`, `distinguishing` | A relação exibe status do precedente e trecho rastreável |
| Validação | `aprovada`, `reprovada`, `requer_revisao`, `marcada_superada` | Evento imutável e auditável |

A Resolução CNJ nº 615/2025 destaca curadoria de dados seguros, rastreáveis e auditáveis, proteção de dados, supervisão humana, transparência, explicabilidade e contestabilidade [6]. Embora a solução seja privada e não substitua decisão judicial, esses controles são adotados como padrão de segurança para a IA jurídica do EJC e para o atendimento simplificado do AcioneJus.

## 6. Pipeline operacional

```text
Pesquisa por lote
  → coleta pública/autorizada
  → snapshot + hash
  → normalização
  → classificação taxonômica
  → validação de legislação e precedente
  → deduplicação por chave/hash/similaridade
  → extração de tese e contratese
  → score determinístico
  → revisão humana
  → publicação no catálogo
  → projeção no RAG
  → monitoramento de alteração/superação
```

A primeira fundação não executa coleta em massa. Ela cria as entidades e os índices que permitem que os lotes futuros tenham checkpoint, idempotência e auditoria. Os conectores oficiais prioritários são LexML, que reúne legislação, jurisprudência, proposições e doutrina em um portal de pesquisa [4]; STJ Dados Abertos, que oferece conjuntos de jurisprudência, consulta processual, gestão de precedentes e DJe com acesso automatizado via CKAN API [3]; DataJud, limitado aos metadados e às regras de uso da fonte [1] [2]; e, para a camada local, TJMG, TRT3 e TRF6, mediante seus portais e APIs/arquivos oficiais efetivamente confirmados antes de cada conector.

## 7. Integração futura com EJC e AcioneJus

No EJC, o catálogo canônico deverá alimentar `Encontrar Teses`, o Motor de Teses, a matriz por caso e o pipeline de peças por meio de uma consulta que filtre `status in (validada, revisada)`, `precedentes.status = validado`, vigência da fonte e escopo de acesso. A seleção humana continuará obrigatória antes de inserir conteúdo em uma peça.

No AcioneJus, a mesma consulta deverá produzir uma visão simplificada, sem expor estratégia interna, dados de clientes, precedentes restritos ou métricas internas. A interface pública poderá receber relato, documentos e classificação preliminar; a camada profissional decidirá quais teses e fontes validadas podem ser utilizadas. O site público afirma operar como plataforma de apoio documental e autoatendimento, não como prestação de advocacia, o que exige manter avisos claros, revisão do usuário e separação entre informação educativa e atuação profissional.

## 8. Riscos e decisões pendentes

| Risco | Tratamento V1 |
|---|---|
| Confundir metadado DataJud com inteiro teor ou resultado final | Campos separados e status de fonte; não marcar como “caso vencedor” apenas por movimentação |
| Usar estimativas do Monitor CDC como estatística nacional | Rótulo de referência interna preservado; fora do catálogo nacional |
| Citar versão revogada ou superada | Snapshots versionados, vigência e alerta de revisão |
| Duplicar tese equivalente | Chave determinística, hash e etapa posterior de similaridade semântica com revisão |
| Vazamento de segredo de justiça/PII | Dados públicos minimizados, sem ingestão de segredo, escopo e logs de acesso |
| Score interpretado como probabilidade | Nome “força jurídica”, fórmula documentada e aviso obrigatório |
| Alteração jurisprudencial | Radar futuro sobre fontes/snapshots e status `superada`/`revisar` |
| Integração privada AcioneJus não auditável | Bloqueada até disponibilização do repositório/contrato de API correspondente |

A LGPD exige finalidade, adequação, necessidade, transparência, segurança, prevenção e responsabilização, além de abranger operações de tratamento em meios digitais [5]. Por isso, nenhum campo de processo sigiloso ou PII desnecessária será usado como matéria-prima pública do catálogo.

## 9. Critério de conclusão deste ciclo

Este ciclo será considerado concluído apenas quando a migração aditiva for revisada, os modelos forem registrados no metadata do Alembic, os testes de domínio e de deduplicação passarem e o relatório declarar explicitamente o que não foi executado. A coleta dos primeiros lotes — começando por Consumidor/JEC e fraude bancária — somente deve iniciar depois da validação do schema e do contrato de fontes.

## Referências

[1]: https://datajud-wiki.cnj.jus.br/api-publica/ "DataJud-Wiki — API Pública"
[2]: https://atos.cnj.jus.br/atos/detalhar/3453 "CNJ — Portaria nº 160/2020, texto e alterações"
[3]: https://dadosabertos.web.stj.jus.br/ "STJ — Portal de Dados Abertos"
[4]: https://www.lexml.gov.br/ "LexML Brasil — Rede de Informação Legislativa e Jurídica"
[5]: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm "Planalto — Lei nº 13.709/2018, texto compilado"
[6]: https://atos.cnj.jus.br/files/original1555302025031467d4517244566.pdf "CNJ — Resolução nº 615/2025"
