# EJC — Roteiro formal de homologação final

**Finalidade:** produzir evidência auditável para os gates G3, G5, G7 e G8 do documento `EJC_10_10_ACCEPTANCE_GATE.md`.

**Regra:** homologação não é demonstração informal. Cada cenário deve registrar executor, papel, horário, dados fictícios utilizados, resultado esperado, resultado observado, evidência e decisão.

## 1. Pré-condições

- [ ] ambiente de homologação separado da produção;
- [ ] versão/commit exato registrado;
- [ ] migrations aplicadas em banco vazio;
- [ ] usuários fictícios criados para todos os papéis;
- [ ] dados pessoais reais proibidos ou previamente anonimizados;
- [ ] integrações externas configuradas em sandbox quando disponível;
- [ ] logs, auditoria e correlação de requisições habilitados;
- [ ] plano de limpeza dos dados de teste definido;
- [ ] responsáveis técnico, jurídico e operacional identificados.

## 2. Matriz mínima de papéis

| Papel | Escopo principal a validar |
|---|---|
| `superadmin` | configuração, governança, auditoria e acesso institucional |
| `admin` | administração operacional e gestão |
| `socio` | visão institucional, aprovações e financeiro |
| `advogado` | carteira própria, casos e produção jurídica |
| `advogado_auxiliar` | somente casos em que foi vinculado |
| `secretaria` | CRM, atendimentos, documentos e agenda permitidos |
| `financeiro` | honorários e pagamentos, sem exposição jurídica indevida |
| `estagiario` | acesso mínimo e restrito aos vínculos autorizados |
| `cliente_externo` | somente portal e dados próprios |

## 3. Padrão de registro por cenário

Para cada cenário, preencher:

- **ID:**
- **Data e horário:**
- **Commit/release:**
- **Executor:**
- **Papel testado:**
- **Dados fictícios utilizados:**
- **Resultado esperado:**
- **Resultado observado:**
- **Evidência:** captura, ID de auditoria, log sanitizado ou relatório automatizado;
- **Tempo total:**
- **Classificação:** aprovado, aprovado com ressalva ou reprovado;
- **Issue corretiva:** obrigatória em caso de falha;
- **Revalidação:** commit e data em que o cenário voltou a passar.

## 4. Cenários obrigatórios

### H01 — Login, 2FA e sessão

1. entrar com papel sujeito a 2FA ainda não configurado;
2. confirmar que apenas o fluxo de ativação é permitido;
3. tentar acessar rota de negócio e confirmar bloqueio;
4. configurar TOTP;
5. entrar com código válido;
6. testar código inválido, expirado e replay;
7. trocar senha e confirmar invalidação das sessões anteriores;
8. encerrar sessão e confirmar rejeição do refresh token reutilizado.

**Aceite:** nenhuma sessão plena antes do TOTP; eventos relevantes auditados; mensagens não expõem segredo.

### H02 — Cliente, conflito e segregação de carteira

1. cadastrar cliente fictício PF e PJ;
2. executar verificação de conflito antes do caso;
3. criar cliente com advogado responsável;
4. testar listagem e detalhe por advogado não vinculado;
5. testar secretaria, financeiro, estagiário e auxiliar;
6. pesquisar por nome e documento;
7. confirmar mascaramento e censura conforme papel;
8. validar trilha da consulta de conflito.

**Aceite:** nenhuma PII integral fora da matriz autorizada; conflito cruza a base sem revelar indevidamente a carteira.

### H03 — Entrada por documento e criação assistida do caso

1. importar documento fictício representativo;
2. validar arquivo, OCR/parsing e extração;
3. revisar partes, fatos, pedidos, área e documentos pendentes;
4. rejeitar um campo sugerido e corrigir manualmente;
5. confirmar criação do cliente e do caso;
6. validar continuidade automática na Jornada;
7. simular falha de anexo e retomar sem duplicar o caso;
8. confirmar que a IA não aplica dados sem revisão humana.

**Aceite:** rascunho claramente identificado, sem duplicidade e com auditoria da decisão humana.

### H04 — Cadastro manual simples

1. criar cliente e caso sem IA;
2. selecionar área de atuação canônica;
3. definir responsável e auxiliar;
4. anexar documento contextual;
5. criar primeira tarefa;
6. confirmar abertura na Jornada;
7. editar e arquivar/desarquivar o caso.

**Aceite:** fluxo completo sem dependência de provedor de IA.

### H05 — Processo principal e acessórios

1. criar processo principal com número CNJ válido;
2. criar recurso/acessório vinculado;
3. promover outro processo a principal;
4. testar criação concorrente ou troca de principal;
5. arquivar principal e validar regra de substituição;
6. desarquivar;
7. confirmar espelho legado compatível;
8. testar acesso por usuário de outra carteira.

**Aceite:** um único principal ativo, sem erro 500, ownership e auditoria preservados.

### H06 — Intimação, prazo, tarefa e agenda

1. cadastrar ou importar intimação fictícia;
2. calcular prazo com parâmetros informados;
3. revisar termo inicial, suspensão e vencimento;
4. criar tarefa e evento vinculados ao caso;
5. atribuir conforme papel permitido;
6. concluir tarefa e prazo;
7. confirmar dashboard e alertas;
8. testar indisponibilidade da IA.

**Aceite:** vínculo único, datas rastreáveis e operação básica independente de IA.

### H07 — Documento, prova, estratégia, tese e peça

1. anexar documento e prova ao caso;
2. classificar e relacionar fatos × provas;
3. gerar estratégia e tese como rascunho;
4. consultar RAG sem cruzamento de carteira;
5. gerar peça;
6. revisar, versionar e aprovar;
7. vincular comprovante de protocolo do mesmo caso;
8. tentar vincular documento de outro caso.

**Aceite:** isolamento, versionamento, HITL e gate de protocolo efetivos.

### H08 — Audiência e atendimento

1. registrar atendimento com data, hora, recado, solicitação e status;
2. criar audiência vinculada;
3. gerar roteiro;
4. registrar ata e providências;
5. criar tarefas/documentos pendentes;
6. confirmar timeline do cliente e do caso;
7. testar edição e auditoria.

**Aceite:** continuidade entre atendimento, audiência, providências e responsável.

### H09 — Honorários e pagamentos

1. criar proposta/honorário vinculado ao caso;
2. criar honorário avulso com papel autorizado;
3. tentar mutação com papel não fiduciário;
4. registrar pagamento parcial;
5. quitar e conciliar;
6. validar KPIs do financeiro;
7. confirmar visão do advogado apenas sobre casos próprios;
8. cancelar com soft delete e auditoria.

**Aceite:** segregação financeira, valores consistentes e histórico auditável.

### H10 — Raio-X avulso e conversão em caso

1. importar processo/documento sem criar caso;
2. gerar síntese, cronologia, riscos e próximos passos;
3. revisar a análise;
4. manter o Raio-X avulso sem incorporá-lo;
5. usar “Transformar em caso”;
6. confirmar reaproveitamento sem duplicidade;
7. validar cliente, documentos e estratégia resultantes.

**Aceite:** decisão explícita do advogado e conversão íntegra.

### H11 — DataJud e impacto cognitivo

1. consultar processo fictício ou autorizado;
2. importar capa e movimentações;
3. confirmar deduplicação;
4. sinalizar alteração relevante;
5. revisar impacto em prazo, estratégia e timeline;
6. simular indisponibilidade/erro externo;
7. confirmar retry controlado e ausência de mutação silenciosa.

**Aceite:** dados externos não substituem decisão humana e não bloqueiam operação essencial.

### H12 — Portal do cliente

1. entrar como cliente externo;
2. visualizar apenas casos próprios;
3. consultar documentos, financeiro, mensagens e assinaturas permitidos;
4. tentar URL/ID de outro cliente;
5. enviar mensagem/documento;
6. confirmar reflexo no escritório e auditoria;
7. testar expiração de sessão.

**Aceite:** zero IDOR e nenhuma exposição de carteira alheia.

### H13 — Backup, restauração e retomada

1. configurar service account exclusiva;
2. compartilhar somente a pasta de backup como Editor;
3. executar backup manual;
4. confirmar artefatos cifrados de banco e uploads;
5. verificar retenção;
6. baixar artefatos em ambiente isolado;
7. descriptografar com chave custodiante;
8. restaurar PostgreSQL em banco vazio;
9. restaurar uploads e verificar amostra;
10. subir aplicação restaurada e executar smoke funcional;
11. registrar tempos e definir RPO/RTO;
12. simular falha e confirmar alerta.

**Aceite:** restauração utilizável, não apenas existência de arquivo remoto.

### H14 — Deploy e rollback

1. registrar commit homologado;
2. executar backup pré-deploy;
3. aplicar migrations;
4. verificar health checks e smoke;
5. induzir falha controlada em ambiente de homologação;
6. executar rollback;
7. confirmar banco, aplicação e arquivos consistentes;
8. registrar duração e decisão.

**Aceite:** retorno comprovado ao estado estável sem perda de dados.

### H15 — Usabilidade e desempenho

1. advogado não técnico executa entrada manual e por documento;
2. localiza próximas ações no dashboard;
3. conclui tarefa, prazo, peça e atendimento;
4. usa ajuda contextual;
5. registra dúvidas, cliques desnecessários e ambiguidades;
6. mede tempos dos fluxos H03, H04, H06, H07 e H09;
7. testa resolução de tela e navegação por teclado nos fluxos principais.

**Aceite:** zero bloqueador e limites de tempo aprovados pelo titular do produto.

## 5. Critérios de suspensão imediata

Suspender a homologação e abrir issue P0 quando houver:

- exposição de dados de outra carteira ou cliente;
- acesso sem autorização a documento, honorário ou processo;
- perda, duplicação ou corrupção de dados;
- prazo calculado ou vinculado sem rastreabilidade;
- protocolo ou comunicação aplicada sem revisão humana;
- segredo em log, resposta, repositório ou artefato;
- backup sem criptografia ou restauração inviável;
- falha que impeça rollback seguro.

## 6. Ata de homologação

A ata final deve conter:

- release e commit exato;
- ambiente e período da homologação;
- executores e papéis;
- cenários aprovados, ressalvas e reprovações;
- issues abertas e riscos formalmente aceitos;
- resultados de backup/restauração e rollback;
- tempos dos fluxos críticos;
- decisão: rejeitada, homologada para piloto ou homologada para produção;
- aprovação do responsável técnico;
- aprovação do responsável jurídico/LGPD;
- aprovação do titular do produto.

**Proibição:** não emitir certificação 10/10 com cenário obrigatório pendente, issue P0/P1 sem tratamento ou risco não formalizado.
