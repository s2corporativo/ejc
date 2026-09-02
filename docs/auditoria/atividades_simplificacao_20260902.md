# Central de Atividades — simplificação operacional (2026-09-02)

## Objetivo
Reduzir carga cognitiva do módulo Agenda/Prazos sem fundir domínios jurídicos no banco e sem retirar gates de backend.

## Arquitetura preservada
- `vw_atividades` continua como fonte agregadora principal.
- `deadlines`, `tasks`, `agenda_eventos`, intimações e suspensões continuam com contratos e persistências próprios.
- autorização permanece no backend; filtros React não são usados como barreira de acesso.
- a implementação anterior `CentralAtividades.tsx` permanece no repositório para rollback imediato.

## Nova experiência
A Central passa a expor quatro eixos operacionais:
1. **Hoje** — pendências vencidas e vencendo no dia;
2. **Próximos** — atividades abertas futuras e sem data;
3. **Caixa de Entrada** — intimações pendentes, prazos a conferir e atrasos que exigem decisão;
4. **Calendário** — visão mensal única.

## Radar
Quatro indicadores acionáveis:
- vencendo hoje;
- aguardando conferência;
- intimações pendentes;
- coincidências de agenda.

A detecção de agenda permanece explicitamente limitada ao contrato legado (mesma data + mesmo horário inicial + mesmo responsável). O frontend informa essa limitação e não apresenta o resultado como sobreposição temporal completa.

## Criação simplificada
O botão **Novo** expõe somente:
- Prazo;
- Tarefa;
- Compromisso.

Audiência, reunião e diligência são subtipos de compromisso. Suspensão sai da criação diária e fica em **Ferramentas → Calendário jurídico**, somente quando o papel já permitido pelo backend também permite a ação.

## Formulários progressivos
Campos essenciais aparecem primeiro. Campos adicionais ficam em **Mais opções**.

Para prazo processual:
- regime é explícito;
- prazo crítico exige termo inicial;
- cronologia publicação → termo inicial → vencimento é validada no cliente como conveniência, sem substituir validação do backend;
- a segunda conferência continua no endpoint canônico e nunca é simulada pelo frontend.

## Funcionalidades preservadas
- concluir;
- registrar ciência;
- confirmar/conferir prazo;
- reagendar;
- atribuir responsável;
- tratar intimação e revisar prazo sugerido;
- buscar DJEN;
- simular prazo;
- exportar prazos CSV;
- administrar suspensão para perfis autorizados;
- vínculo contextual com caso.

## Status unificado de UX
A interface traduz estados heterogêneos para:
- Pendente;
- Em andamento;
- Concluído;
- Cancelado;
- Atrasado;
- Aguardando conferência.

Os status físicos originais continuam preservados em cada domínio.

## Prazo crítico
Prazo crítico exibe fluxo visual:
`Calculado → Conferido → Execução → Conclusão`.

O componente apenas representa evidência recebida do backend (`calculado_por`, `conferido_por`, status). Não concede conferência nem infere autoria.

## Segurança / LGPD
- nenhuma nova PII persistida;
- nenhuma credencial;
- nenhuma regra de RBAC somente no frontend;
- pesquisa ocorre somente sobre dados já devolvidos ao usuário pelo backend;
- coincidências de agenda são calculadas somente sobre eventos já autorizados no feed do usuário;
- nenhum conteúdo integral de intimação é incluído em log novo.

## Agenda v2
Duração, recorrência e lembretes já possuem motor puro preparado na branch anterior, mas a persistência permanece bloqueada até a migration 156 integrar a `main` e o ledger Alembic liberar o próximo número real. Nenhuma migration 157 é criada nesta branch.

## Testes adicionados
`frontend/src/pages/CentralAtividades/simplificacao.test.ts` cobre:
- normalização de status;
- caixa de entrada de prazo crítico;
- prazo crítico concluído não reabre por UI;
- colisões legadas por responsável/data/hora;
- busca unificada por título/caso/responsável.

## Rollback
Alterar `frontend/src/pages/Central.tsx` para voltar a importar/renderizar `./CentralAtividades`. Nenhuma alteração de banco precisa ser desfeita.

## Gate de integração
Esta branch está empilhada sobre a Agenda #1342. Não deve ser integrada em produção enquanto a cadeia P0/P1/#968/#717/#1342 estiver com CI vermelho ou H06 pendente.
