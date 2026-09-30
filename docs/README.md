# Documentação canônica do EJC

Este índice separa fonte operacional atual de histórico. Agentes e pessoas
devem começar por estes documentos; materiais em docs/arquivo/ são evidência
histórica e não devem orientar implementação nova sem reconfirmação no código.

## Arquitetura e fluxo
- ARQUITETURA_ATUAL.md — arquitetura vigente.
- FLUXO_CANONICO_EJC.md — jornada jurídica canônica.
- MAPA_DE_MODULOS.md — mapa funcional dos módulos.
- decisoes/ — ADRs vigentes.

## IA jurídica
- ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md — núcleo único de IA.
- ai/EJC_AI_PROVIDER_POLICY.md — política de providers.
- ai/EJC_AI_HITL_POLICY.md — revisão humana.
- ai/EJC_AI_SECURITY_LGPD_POLICY.md — segurança e sigilo.
- GOVERNANCA_IA.md — governança geral.

## Operação, CI e deploy
- DEPLOY-VPS.md — deploy vigente.
- RUNBOOK_CERTIFICACAO_RELEASE_EJC.md — certificação de release.
- BACKUP_RESTORE_RUNBOOK.md — backup/restore.
- observabilidade.md — observabilidade.
- .woodpecker.yml e infra/host-automation/ — fonte executável da automação.

## Produto e interface
- PLANO_SIMPLIFICACAO_EJC.md — direção de simplificação.
- DESIGN_SYSTEM_EJC.md e FRONTEND_DESIGN_SYSTEM.md — design.
- DESENHO_ENTRADA_UNICA_E_CASO_WORKSPACE.md — Entrada Única/Caso.

## Status controlado
- PLANO_MESTRE_STATUS.md — ainda é consumido pelos scripts de status e permanece canônico até aposentadoria explícita.
- CRITERIOS_DE_ACEITE.md e RELEASE_CHECKLIST.md — critérios de promoção.

## Histórico
- arquivo/ — planos, relatórios, auditorias e publicações superados.
- audit/, auditoria/, consolidacao/ ainda possuem referências no código; permanecem no lugar até essas referências serem eliminadas de forma versionada.

Regra: código e testes prevalecem sobre prosa histórica. Se um documento
não estiver neste índice, confirme sua validade antes de usá-lo como instrução.
