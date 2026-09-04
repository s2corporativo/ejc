# Critérios de aceite — auditoria de Pull Request

Todo PR do EJC é auditado em cinco camadas, **aplicadas proporcionalmente ao diff**: só as
camadas que a mudança toca são exigidas (docs-only dispensa A/C/D/E técnicas; mudança sem UI
dispensa D; sem regra jurídica dispensa C). Um "não" em qualquer camada aplicável impede o
merge. Regras canônicas em `docs/GOVERNANCA_IA.md` (v4.0).

## A. Correção técnica

- [ ] O código compila e a aplicação sobe (`npm run build`, import do backend sem erro).
- [ ] Testes do escopo passam; a suíte não regride.
- [ ] Tipagem correta (`tsc --noEmit` limpo; anotações coerentes no backend).
- [ ] Rotas do frontend correspondem a endpoints existentes (sem `/api` duplicado, sem
      prefixo `/v1` redundante).
- [ ] Migrations lineares, head único, `down_revision` correto.
- [ ] Sem import quebrado, sem código morto deixado para trás.
- [ ] Erros tratados: falha externa degrada com mensagem útil, não com 500 silencioso.
- [ ] Lint limpo (`ruff check app`, ESLint).

## B. Segurança

- [ ] RBAC conferido — o endpoint exige o papel certo, nem mais nem menos.
- [ ] Autenticação e sessão: token, refresh e revogação intactos.
- [ ] Isolamento por escritório/usuário/caso preservado (sem IDOR).
- [ ] Nenhum vazamento de dado entre clientes, casos ou portais.
- [ ] Logs e mensagens de erro sem PII, sem segredo, sem conteúdo de mensagem.
- [ ] Uploads validados (tipo, tamanho, hash, varredura quando habilitada).
- [ ] Sem injeção — SQL parametrizado, sem interpolação de entrada em query ou comando.
- [ ] Segredos fora do repositório e fora da query string.
- [ ] Operações de IA: gateway, sanitização, kill-switch, HITL e citation gate intactos.
- [ ] Comportamento **fail-closed** em caso de indisponibilidade (Redis fora, provedor
      fora, flag ausente) — a falta de infraestrutura não pode liberar acesso.

## C. Validade jurídica

Aplicável a toda mudança que produza prazo, cálculo, tese, peça ou orientação.

- [ ] Legislação vigente na data, com a alteração legislativa recente considerada.
- [ ] Fonte oficial citada (lei/artigo, súmula, precedente).
- [ ] Cálculo conferido à mão em ao menos um caso normal e um de borda.
- [ ] Marco inicial e final do prazo corretos; regime de contagem correto (úteis/corridos).
- [ ] Exceções e suspensões tratadas (recesso, feriado, prerrogativa, prazo em dobro).
- [ ] Competência e rito corretos.
- [ ] Aviso de revisão humana visível.
- [ ] Sem afirmação jurídica absoluta indevida.
- [ ] Vigência e versão da regra gravadas na resposta e no documento gerado.
- [ ] Ferramenta não homologada não vira documento formal.

## D. Fluxo funcional

- [ ] Um advogado iniciante consegue concluir a tarefa sem instrução externa.
- [ ] A ação principal da tela está clara e é alcançável.
- [ ] O estado não se perde ao recarregar, voltar ou perder conexão momentânea.
- [ ] O retorno do sistema é compreensível — nada de "Falha no cálculo" sem dizer o quê.
- [ ] O erro orienta a correção (qual campo, qual valor esperado).
- [ ] Não existem caminhos duplicados para a mesma função.
- [ ] Comportamento verificado em largura desktop e móvel quando há mudança de UI.

## E. Regressão

- [ ] Funcionalidade anterior continua operante.
- [ ] Contrato entre frontend e backend mantido (ou atualizado nos dois lados no mesmo PR).
- [ ] Migration funciona em banco novo **e** em banco existente com dado legado.
- [ ] Rollback viável e descrito (código, configuração e banco).
- [ ] Documentos, links e tokens emitidos antes continuam acessíveis — ou a invalidação é
      deliberada, documentada e comunicada.
- [ ] Nenhuma correção anterior foi desfeita por este PR.

## Encerramento

Nenhum PR é aprovado sem relatório — que é o **próprio PR com template preenchido** (§6 regra
11 da governança): arquivos, comandos, testes, evidências, riscos residuais, limitações e
pontos que exigem decisão humana. Não se exige documento separado.
