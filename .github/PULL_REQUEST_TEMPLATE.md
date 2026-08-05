# Pull request template — alterações automáticas

Este pull request foi gerado pela automação na branch `fix/automated-broad-2026-08-05`.

Objetivo
- Aplicar correções automáticas autorizadas (escopo B) no repositório s2corporativo/ejc.

O que este PR pode conter (escopo autorizado)
- Execução de formatadores (prettier / eslint / black / isort) e correções de estilo.
- Correções automáticas de lint e typecheck quando não ambíguas.
- Atualizações agrupadas de dependências compatíveis (separadas por frontend/backend quando aplicável).
- Correções mecânicas determinísticas (validações, whitelist anti-mass-assignment, triggers/DDL idempotente) — sem alterações de produto que exijam teste em VPS.

Atenção e riscos
- Algumas alterações podem alterar comportamento; revise localmente antes de mesclar.
- Mudanças que exigem teste em ambiente real (VPS, integrações) foram documentadas em issues PR/commit e NÃO foram mescladas automaticamente.

Checklist de revisão (marcar antes de mesclar)
- [ ] Verifique os testes locais e E2E relevantes.
- [ ] Confirme mudanças em migrations / DDL (se presentes).
- [ ] Confirme que atualizações de dependências não introduzem breaking changes.
- [ ] Revisar qualquer alteração de segurança ou LGPD.
- [ ] Aprovação final de @s2corporativo (revisor designado).

Nota operacional
- PR criado sem aguardar conclusão dos workflows (opção: não aguardar CI) conforme instrução do maintainer.
- Commits automáticos posteriores a este PR podem ser empurrados para a mesma branch para estabilizar o CI.

Link da branch: https://github.com/s2corporativo/ejc/tree/fix%2Fautomated-broad-2026-08-05

--
GitHub Copilot Chat Assistant — automação autorizada por s2corporativo
