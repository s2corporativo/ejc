# H06 — Gate autenticado de Agenda e Prazos

Este roteiro complementa `docs/EJC_ROTEIRO_HOMOLOGACAO_FINAL.md` e a matriz geral. Ele **não substitui** a homologação humana: organiza as provas técnicas e impede que #381/#1209 sejam encerradas apenas por merge de código.

## Ambiente e segurança

- Executar somente em localhost/staging/homologação ou em produção após aprovação explícita do runbook pós-deploy.
- Usar exclusivamente dados marcados `HOMOLOG-FICTICIO`; nunca CPF, cliente, processo, intimação ou documento real.
- Credenciais são fornecidas por variáveis de ambiente e nunca registradas no Git, relatório ou log.
- Registrar SHA do commit testado e comparar com `/api/health`/runtime quando o ambiente expuser essa informação.

## H06.1 — Cálculo processual canônico

1. Autenticar usuário jurídico fictício.
2. `POST /api/deadlines/calcular` com `tipo=processual`, regime explícito e datas fictícias.
3. Confirmar resposta com regime, vencimento, modo de cálculo, estado do calendário, indicação de preliminar/revisão quando aplicável.
4. Repetir sem `regime_calculo` e exigir 422.
5. Confirmar que `/suspensoes/simular` não é usado pela Central para prazo processual.

**Aceite:** nenhum regime é presumido silenciosamente.

## H06.2 — Ownership e prazo avulso

1. Criar prazo avulso para usuário A.
2. Usuário A deve listar/ler/mutar o próprio prazo.
3. Usuário B, não-gestão, não deve obter o prazo avulso de A; mutação por ID conhecido deve retornar resposta anti-enumeração prevista.
4. Gestão fictícia deve enxergar o prazo conforme RBAC.
5. Tentar atribuir prazo avulso a terceiro sem papel de gestão e exigir bloqueio.

**Aceite:** `case_id IS NULL` nunca equivale a acesso global.

## H06.3 — Prazo crítico e quatro olhos

Após a migration auditável estar aplicada:

1. Criar prazo processual crítico com publicação/termo inicial/regime/vencimento rastreáveis.
2. Confirmar que nasce `confirmado=false` e com `calculado_por` identificado.
3. O calculista tenta `/api/deadlines/{id}/confirmar` e recebe conflito de autoconferência.
4. Segundo usuário autorizado, distinto e com ownership do caso, confirma.
5. Alterar materialmente vencimento/marco/regime/base legal.
6. Confirmar que a conferência anterior é invalidada, o snapshot histórico é preservado e o prazo volta a aguardar conferência.
7. Tentar segunda conferência por usuário sem ownership e exigir bloqueio.

**Aceite:** quatro olhos não cria bypass de RBAC e toda mudança material reabre a conferência.

## H06.4 — DJEN revisado

1. Usar comunicação DJEN inteiramente fictícia no ambiente de homologação.
2. Confirmar que disponibilização capturada é exibida separadamente e não é reinterpretada como publicação/termo inicial.
3. Tentar aceitar sem publicação, termo inicial, regime, vencimento ou confirmação de fonte oficial e exigir 422.
4. Informar os quatro marcos revisados e confirmar vínculo único ao caso.
5. Verificar trilha de auditoria sem teor integral da comunicação.
6. Confirmar que DataJud não materializa Deadline automaticamente.

**Aceite:** prazo DJEN só é materializado após revisão humana explícita dos fatos necessários.

## H06.5 — Tarefa e Agenda

1. Criar tarefa e evento fictícios vinculados ao mesmo caso.
2. Validar atribuição segundo RBAC.
3. Criar conflito de agenda e confirmar aviso sem exposição indevida da agenda alheia.
4. Após Agenda v2 estar ativada, testar sobreposição real de intervalos, bordas encostadas, dia inteiro, timezone, recorrência e lembretes configuráveis.
5. Editar uma ocorrência e uma série conforme UX aprovada.
6. Confirmar ausência de duplicação em reenvio/retry.

**Aceite:** vínculo único, ownership preservado, conflitos rastreáveis e recorrência idempotente.

## H06.6 — Alertas e conclusão

1. Reagendar prazo ou trocar responsável após flags de alerta simuladas.
2. Confirmar reset 7d/3d/1d.
3. Concluir tarefa e prazo.
4. Validar dashboard/Central e notificações esperadas.
5. Simular indisponibilidade de IA e confirmar operação básica independente do provedor.

## Evidências mínimas a registrar

- SHA testado;
- ambiente e data/hora;
- papéis fictícios utilizados, sem credenciais;
- IDs internos fictícios gerados;
- status HTTP e resultado de cada passo;
- capturas de tela apenas se não houver dados reais/sensíveis;
- divergências encontradas e issue correspondente;
- responsável humano pelo aceite final.

## Gate final

H06 só pode ser marcado como concluído quando **todos** os blocos aplicáveis estiverem aprovados no ambiente-alvo e houver aceite humano explícito. Código verde, isoladamente, não fecha #381 nem #1209.
