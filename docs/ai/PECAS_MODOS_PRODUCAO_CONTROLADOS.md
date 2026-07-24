# Modos controlados de produção jurídica

## Finalidade

Organizar a experiência de produção do EJC em quatro modos sem duplicar o
núcleo de IA e sem criar nova assinatura, provider ou banco.

A arquitetura preservada é:

```text
legal_case_orchestrator
        ↓
motor_peca_service (cabimento, checklist e prazo)
        ↓
peca_workflow_service (Livre, Guiado, Molde ou Agente)
        ↓
peca_service.gerar_peca_pipeline (redação em sete etapas)
        ↓
revisão jurídica + aprovação humana
```

`peca_workflow_service` é uma camada determinística. Ele não abre banco, não
chama LLM, não cria prazo e não aprova documento.

## Modo Livre

O advogado fornece uma instrução adicional e utiliza os fatos, pedidos,
documentos, ficha confirmada, teses e RAG já resolvidos pelo fluxo canônico.

A ausência de instrução livre não bloqueia a redação, porque o endpoint atual já
possui fatos e pedidos obrigatórios. A interface deve mostrar um alerta, não
inventar uma exigência nova.

## Modo Guiado

O sistema solicita campos mínimos por tipo de peça. A primeira versão possui
contratos específicos para:

- petição inicial;
- contestação;
- réplica;
- apelação;
- agravo;
- recurso ordinário;
- contrato;
- notificação;
- parecer.

Tipos ainda não mapeados usam o fallback seguro: partes, fatos, provas e pedidos.
O formulário bloqueia a geração enquanto houver campo obrigatório vazio.

## Modo Molde

O molde é uma referência versionada, não texto livre descartável. Para ficar
pronto para uso, exige:

- `documento_id`;
- `versao`;
- `hash_conteudo`;
- lista do que preservar;
- lista do que substituir.

O mesmo campo não pode ser simultaneamente preservado e substituído.

A revisão final deve obrigatoriamente:

- procurar nomes e números do caso anterior;
- procurar documentos não pertencentes ao novo caso;
- verificar datas e valores residuais;
- remover pedidos sem suporte fático atual;
- comparar a estrutura preservada com a peça gerada.

## Modo Agente

O Modo Agente é um workflow determinístico e não um loop autônomo. A ordem é:

1. documentos considerados;
2. fatos identificados;
3. lacunas e documentos faltantes;
4. pedidos e controvérsias;
5. mapa de provas;
6. teses possíveis;
7. pesquisas necessárias;
8. estrutura sugerida;
9. aprovação do advogado;
10. redação e revisão.

A redação fica bloqueada enquanto faltar:

- `case_id` autorizado;
- ao menos um documento considerado;
- aprovação explícita do plano.

A aprovação do plano não equivale à aprovação da peça. O documento gerado
continua como rascunho sujeito ao HITL já existente.

## Integração prevista

A integração com `/pecas/gerar` deverá ocorrer depois da validação deste
contrato. O router deve:

1. validar role e acesso ao caso como já faz hoje;
2. montar `ProducaoModoRequest`;
3. chamar `preparar_modo_producao`;
4. retornar 409/422 quando houver bloqueios;
5. anexar `instrucoes_pipeline` às instruções adicionais;
6. chamar o pipeline de sete etapas já existente;
7. registrar modo, referência do molde e aprovação no `AILog` ou metadado
   auditável existente, sem dados sensíveis em log.

Não devem ser criados endpoints públicos paralelos de geração, outro motor de
peça ou chamadas adicionais obrigatórias de IA.

## Segurança e LGPD

- referências documentais contêm IDs e versão, não o conteúdo integral;
- acesso aos documentos continua sendo validado pela camada chamadora;
- nenhuma referência amplia escopo de cliente ou caso;
- dados fornecidos pelo advogado são marcados como dados, não como instrução de
  sistema, reduzindo risco de prompt injection;
- o Modo Molde exige detector de resíduos antes da aprovação;
- o Modo Agente exige caso e documentos explicitamente autorizados;
- nenhum modo produz documento protocolável sem revisão humana.

## Rollback

A camada é aditiva e ainda não altera o endpoint existente. O rollback consiste
em reverter os arquivos de schema, service, testes e documentação. Não há
migration, dado ou fila a restaurar.
