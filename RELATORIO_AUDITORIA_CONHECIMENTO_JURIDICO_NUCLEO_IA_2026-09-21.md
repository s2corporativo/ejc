# Auditoria do conhecimento jurídico e do núcleo de IA — EJC

**Data:** 21 de setembro de 2026  
**Escopo:** repositório `s2corporativo/ejc`, branch `main`, commit `64bc6363`  
**Foco:** qualidade e governança do conhecimento jurídico, recuperação aumentada por geração (RAG), validação de citações, vigência normativa, proteção de dados e núcleo canônico de IA.

## Conclusão executiva

O EJC apresenta uma **arquitetura de IA juridicamente consciente e tecnicamente madura**. O repositório possui um núcleo canônico de orquestração, contratos explícitos para evidências, isolamento por caso e cliente, gates de citação, controle de vigência, sanitização de dados pessoais, revisão humana obrigatória e uma suíte focal consistente. A execução dos testes selecionados terminou com **90 aprovados, 4 ignorados e nenhuma falha**.

A principal limitação não está na ausência de mecanismos de segurança. Está na **ausência de um corpus jurídico humano, real, pseudonimizado e atestado**, usado para medir se o sistema recupera a autoridade correta e se produz análises juridicamente adequadas. O próprio smoke test confirma que os arquivos atuais são exemplos ou candidatos não atestados e, portanto, não certificam qualidade jurídica de nenhuma área.

Minha avaliação geral é: **núcleo estrutural forte; qualidade jurídica ainda não certificável em produção**. O sistema deve ser tratado como gerador de rascunhos com revisão profissional, e não como mecanismo autônomo de fundamentação ou prognóstico.

## Achados prioritários

| ID | Severidade | Achado | Impacto | Recomendação |
|---|---|---|---|---|
| JUR-01 | **P0 — bloqueia certificação** | Não há gold set jurídico real atestado no repositório. O `run_eval --smoke` reporta cobertura zero de áreas reais. | Não é possível medir precisão de recuperação, adequação de tese, correção de citações ou comportamento em casos normais, de fronteira e de exceção. | Curar o conjunto institucional mínimo exigido pelo próprio projeto: 75 casos reais, 15 por área em cinco áreas, com cenários normal/fronteira/exceção, fontes oficiais, vigência conferida e curador identificado. Executar o gate `gold_governance` antes de liberar qualquer indicador de qualidade. |
| JUR-02 | **P1 — qualidade** | A verificação de pertinência da citação está desligada por padrão (`PERTINENCIA_ENABLED=false`). | O sistema valida existência, formato e alguns sinais de vigência, mas não verifica por padrão se a autoridade realmente sustenta a proposição afirmada na peça. | Depois de existir corpus jurídico suficiente, medir custo e taxa de falso positivo e ligar progressivamente a pertinência para peças e análises de maior risco. Manter desligada para endpoints que prometem validação local sem LLM. |
| JUR-03 | **P1 — qualidade** | O modo estrito de citações está desligado (`CITACOES_MODO_ESTRITO=false`). | Artigo ou súmula ausente da base curada pode ser sinalizado, mas não necessariamente bloqueado. A proteção depende do revisor e da abrangência da base. | Expandir a base normativa e jurisprudencial oficial, medir impacto e ativar o modo estrito por tipo de fluxo, começando por aprovação/protocolo de peças. |
| JUR-04 | **P1 — recuperação** | Reranking cross-encoder está desligado (`RAG_RERANK_ENABLED=false`). | A recuperação usa busca vetorial e lexical/RRF, mas não recebe a etapa adicional de reordenação semântica. Em consultas jurídicas ambíguas, isso pode reduzir a precisão do contexto. | Não ligar sem avaliar licença e desempenho em português jurídico. Selecionar modelo com licença comercial compatível, comparar nDCG/recall@k/MRR contra o gold set e liberar gradualmente. |
| JUR-05 | **P1 — governança de conhecimento** | Os ingestores oficiais e a governança existem, mas a inspeção local não comprova que a base de produção está abrangente, atualizada e aprovada. | Importar jurisprudência não equivale a liberar conteúdo para contexto ou citação; uma base incompleta pode gerar ausência de fonte ou dependência excessiva de revisão manual. | Criar painel operacional com cobertura por área/tribunal/tipo de fonte, idade da última atualização, documentos em quarentena, vigência não verificada e taxa de recuperação sem fonte. Definir SLOs de frescor e cobertura. |
| JUR-06 | **P1 — operação** | A configuração em exemplo contém fallback externo para intake e múltiplos provedores, com regras corretas descritas, mas a eficácia depende do `.env` de produção e do estado do Ollama. | Se a configuração divergir do exemplo, conteúdo sensível pode seguir por rota externa ou a área pode ficar indisponível sem visibilidade suficiente. | Certificar configuração efetiva por ambiente. Exigir teste de startup que confirme `AI_REQUIRE_HITL`, política de citações, modo de sanitização por tarefa, kill-switch, elegibilidade dos provedores e disponibilidade de IA local para sigilo reforçado. |
| JUR-07 | **P2 — avaliação** | Os testes cobrem contratos e regressões, mas não substituem avaliação de qualidade jurídica. | Testes unitários podem provar que o gate bloqueia uma citação inválida sem provar que a tese recuperada é a melhor, atual ou aplicável ao caso. | Separar claramente testes de segurança/contrato de testes de qualidade jurídica. Publicar métricas por área e cenário, com limiares de aprovação e amostras de erro revisadas por advogado. |

## O que está bem implementado

O **núcleo canônico** está bem delineado. O orquestrador concentra a execução e aplica pipeline de contexto, skills, validação de resposta, auditoria e política de revisão. O registro de agentes parametriza capacidades sem criar uma implementação paralela para cada agente. Esse desenho reduz divergência entre portas antigas e novas.

A camada de evidência jurídica é um ponto forte. O contrato diferencia estados como não verificado, confirmado e validado por advogado. Promoções para estados validados exigem revisor autenticado e data. O estado de uma proposição também não é presumido pela ausência de relações: sem proveniência explícita, o resultado é `nao_verificada`. Isso evita transformar silêncio do grafo em validade jurídica.

A recuperação RAG aplica filtros importantes antes de entregar contexto ao modelo. O código filtra documentos excluídos, exige embedding, respeita escopo de cliente/caso, considera vigência e utiliza o status de governança. A estratégia combina vetor, busca lexical e fusão RRF. O chunker diferencia legislação, jurisprudência estruturada, teses, pedidos e conteúdo geral, preservando cabeçalhos e impondo teto de tamanho.

A validação de citações também está acima do padrão de um protótipo. O sistema distingue existência de pertinência, identifica artigos e súmulas, verifica sinais de desatualização, pode consultar fontes externas de confirmação de jurisprudência e aplica política de bloqueio na aprovação HITL. O código evita tratar “não verificado” como equivalente a “comprovadamente errado”, o que é uma escolha conservadora e operacionalmente adequada quando a base ainda possui lacunas.

A proteção de dados é coerente com o risco jurídico. Há modos de sanitização local, pseudonimização reversível, mascaramento e extração local. Áreas sensíveis podem exigir IA local em modo fail-closed. O repositório também registra que o fallback externo implica transferência internacional e que a decisão de permitir isso deve ser do titular responsável pelo tratamento.

## Limitações materiais do conhecimento jurídico

O projeto dispõe de runbooks para importar fontes oficiais, inclusive LexML, STJ e TJMG, e possui mecanismos de quarentena, aprovação, deduplicação, vigência e proveniência. Isso demonstra que o caminho operacional foi desenhado. Porém, a auditoria do repositório não pode afirmar que a base efetivamente contém cobertura suficiente em produção, porque os dados operacionais e a configuração real não estão disponíveis neste clone.

O resultado do comando `python -m app.eval.run_eval --smoke` é decisivo: os arquivos encontrados são exemplos de formato e 10 candidatos não atestados. A saída informa expressamente que **nenhum gold set real está disponível** e que o resultado não afere a qualidade jurídica de nenhuma área. O backlog de curadoria também deixa os casos requeridos como pendentes.

Há ainda um risco conceitual importante: fonte oficial não é sinônimo de texto vigente nem de gabarito correto. O próprio material de curadoria alerta que uma publicação oficial original pode conter numeração histórica, enquanto a redação atual decorre de alteração legislativa posterior. Portanto, a ingestão precisa guardar não apenas URL, tribunal e data de consulta, mas também versão reconstruível, situação normativa e conferência humana do conteúdo usado como gabarito.

## Avaliação do núcleo de IA

O núcleo tem **boa separação de responsabilidades** entre gateway de provedores, roteador, política de sanitização, construção de contexto, orquestração, validação e auditoria. A seleção de provedor passa por elegibilidade e kill-switch. A configuração privilegia provedores externos fortes, mas mantém Ollama como possibilidade de soberania de dados e fallback conforme o ambiente.

O comportamento de falha é, em geral, apropriado para o domínio. Quando não há fonte verificável, o resultado é marcado e a revisão é obrigatória, em vez de a aplicação criar uma fonte fictícia. Quando a IA fica indisponível, funções que possuem dados objetivos, como jurimetria real, preservam o dado e removem sugestões gerativas. Os testes também verificam que jurisprudência ausente no RAG não é substituída por links fictícios.

A maior dívida do núcleo é de **calibração empírica**, não de desenho. O threshold de similaridade, o número de resultados, a escolha de HyDE e a eventual ativação do reranker são configuráveis, mas não estão vinculados a um conjunto jurídico atestado que permita escolher os valores por evidência. O HyDE está ligado por padrão e adiciona uma chamada de IA por busca; isso deve ser avaliado em latência, custo, recall e risco de desvio semântico em consultas com artigo, súmula ou número processual.

## Testes e verificações executadas

Foram executados os seguintes controles:

- `python3 -m pytest -q` sobre oito arquivos focais de cérebro jurídico, RAG, citações, vigência, qualidade e veredito: **90 passed, 4 skipped**.
- `python3 -m app.eval.run_eval --smoke`: **formato válido**, porém **sem gold set real** e sem cobertura jurídica certificada.
- `python3 -m compileall -q backend/app backend/tests`: **sucesso**.
- Inspeção estática dos módulos `legal_brain`, `ai_gateway`, `citation_gate`, `citation_check`, `knowledge_governance`, `legal_base`, `legal_chunker`, `ai_service` e políticas de sanitização.

A primeira tentativa de teste falhou por dependência ausente (`pydantic_settings`); após instalar `backend/requirements.txt`, a suíte focal executou normalmente. O ambiente emitiu um aviso de segurança operacional: `VAULT_MASTER_KEYS` não estava definida, então uma chave Fernet efêmera foi gerada. Isso não falhou nos testes, mas **não é aceitável em produção**, pois credenciais cifradas poderiam tornar-se ilegíveis após reinício.

## Plano recomendado

### Imediato — antes de certificar qualidade

A prioridade deve ser concluir o gold set humano. O conjunto deve conter casos reais pseudonimizados, gabaritos jurídicos conferidos, fontes oficiais HTTPS, vigência registrada e cobertura por área e cenário. O gate deve falhar quando uma área obrigatória estiver ausente, mesmo que os testes de formato estejam verdes.

Em paralelo, deve-se criar um comando de diagnóstico de produção que mostre a configuração efetiva sem revelar segredos. Esse diagnóstico precisa incluir o provedor realmente elegível, a política de sanitização aplicada, a disponibilidade de IA local, o status de HITL, a política de citações e a idade/cobertura da base jurídica.

### Curto prazo — depois do gold set mínimo

Executar benchmark de recuperação por área com `recall@k`, `precision@k`, `MRR` ou `nDCG`, separado por legislação, jurisprudência, súmulas e teses. Medir também documentos fora de vigência retornados indevidamente e consultas sem resposta correta. Só então escolher `RAG_MIN_SIM`, limite de resultados, peso lexical, HyDE e reranking.

Ativar a pertinência de citações em um fluxo piloto de alto risco e revisar manualmente os falsos positivos. Depois, considerar o modo estrito para aprovação de peças, sempre preservando uma rota de override justificado e auditado por advogado.

### Médio prazo — operação contínua

Instituir revisão periódica da base com indicadores de frescor, fontes em erro, quarentena, duplicatas, vigência não verificada, jurisprudência superada e taxa de respostas sem âncora. O painel deve separar claramente “fonte oficial”, “fonte aprovada internamente” e “força jurídica”, pois essas propriedades não são equivalentes.

## Veredito

**Aprovado com ressalvas para uso como sistema de apoio e rascunho sob revisão humana. Não aprovado como sistema juridicamente certificado ou autônomo.**

O código demonstra boas decisões de segurança e governança. O bloqueio para uma conclusão mais forte é a falta de evidência jurídica externa ao código: sem casos humanos atestados e sem benchmark real, não há base para afirmar que o EJC recupera a norma correta, interpreta a jurisprudência de modo adequado ou mantém desempenho confiável nas cinco áreas prioritárias.

## Referências

[1]: https://github.com/s2corporativo/ejc/blob/main/backend/app/services/ai/core/orchestrator.py "Orquestrador canônico do núcleo de IA"

[2]: https://github.com/s2corporativo/ejc/blob/main/backend/app/services/legal_brain/contracts.py "Contratos de evidência e estado jurídico"

[3]: https://github.com/s2corporativo/ejc/blob/main/backend/app/services/ai_service.py "Recuperação RAG e montagem de fontes"

[4]: https://github.com/s2corporativo/ejc/blob/main/backend/app/services/citation_gate.py "Gate de aprovação e validação de citações"

[5]: https://github.com/s2corporativo/ejc/blob/main/backend/app/eval/run_eval.py "Runner de avaliação e smoke test dos gold sets"

[6]: https://github.com/s2corporativo/ejc/blob/main/backend/app/eval/GOLD_SET_GOVERNANCE.md "Governança do gold set jurídico"

[7]: https://github.com/s2corporativo/ejc/blob/main/docs/ai/AUDITORIA_APIS_IA_E_NIVEL_INTELIGENCIA_2026-08-18.md "Auditoria de APIs de IA e nível de inteligência"

[8]: https://github.com/s2corporativo/ejc/blob/main/backend/app/core/config.py "Configuração de HITL, citações e recuperação"
