# Backlog — Gold Set Jurídico Humano do EJC

Este arquivo é **fila de curadoria**, não corpus de avaliação. Nenhuma linha abaixo conta para o gate `gold_governance`; somente casos reais, pseudonimizados e versionados em `gold_set*.jsonl`, validados pelo código, podem contar.

## Gate institucional atual

O workflow `EJC Legal Quality Certification` exige:

- 75 casos humanos reais;
- 15 por área: `consumidor`, `trabalhista`, `civel`, `penal`, `tributario`;
- em cada área, no mínimo 5 cenários `normal`, 5 `fronteira` e 5 `excecao`;
- `ficticio=false`;
- curador e revisor distintos;
- datas de revisão e de conferência de vigência;
- ao menos uma fonte oficial HTTPS com versão reconstruível;
- ausência de PII e placeholders;
- payload avaliável de RAG (`query` + `expected_titulos`) ou peça (`fatos` + tipo/tese/critérios).

**Casos inventados por IA não satisfazem este gate.** A IA pode ajudar a formatar um caso já curado, mas não pode criar o fato jurídico nem atestar a correção do gabarito.

## Processo de curadoria

1. selecionar caso/pergunta real e relevante ao escritório;
2. pseudonimizar antes de versionar;
3. definir cenário e área;
4. curador jurídico monta o gabarito;
5. conferir legislação/jurisprudência em fonte oficial vigente;
6. revisor independente confere fatos, tese, citações, pedido e limites;
7. registrar somente identidades funcionais/institucionais de curador e revisor — nunca credenciais;
8. rodar `python -m app.eval.gold_governance --require-real ...`;
9. somente após gate verde usar o corpus como certificação.

## Consumidor — 15

| ID | Cenário | Curadoria | Revisão | Status |
|---|---|---|---|---|
| CON-001 | normal | — | — | pendente |
| CON-002 | normal | — | — | pendente |
| CON-003 | normal | — | — | pendente |
| CON-004 | normal | — | — | pendente |
| CON-005 | normal | — | — | pendente |
| CON-006 | fronteira | — | — | pendente |
| CON-007 | fronteira | — | — | pendente |
| CON-008 | fronteira | — | — | pendente |
| CON-009 | fronteira | — | — | pendente |
| CON-010 | fronteira | — | — | pendente |
| CON-011 | excecao | — | — | pendente |
| CON-012 | excecao | — | — | pendente |
| CON-013 | excecao | — | — | pendente |
| CON-014 | excecao | — | — | pendente |
| CON-015 | excecao | — | — | pendente |

## Trabalhista — 15

| ID | Cenário | Curadoria | Revisão | Status |
|---|---|---|---|---|
| TRA-001 | normal | — | — | pendente |
| TRA-002 | normal | — | — | pendente |
| TRA-003 | normal | — | — | pendente |
| TRA-004 | normal | — | — | pendente |
| TRA-005 | normal | — | — | pendente |
| TRA-006 | fronteira | — | — | pendente |
| TRA-007 | fronteira | — | — | pendente |
| TRA-008 | fronteira | — | — | pendente |
| TRA-009 | fronteira | — | — | pendente |
| TRA-010 | fronteira | — | — | pendente |
| TRA-011 | excecao | — | — | pendente |
| TRA-012 | excecao | — | — | pendente |
| TRA-013 | excecao | — | — | pendente |
| TRA-014 | excecao | — | — | pendente |
| TRA-015 | excecao | — | — | pendente |

## Cível — 15

| ID | Cenário | Curadoria | Revisão | Status |
|---|---|---|---|---|
| CIV-001 | normal | — | — | pendente |
| CIV-002 | normal | — | — | pendente |
| CIV-003 | normal | — | — | pendente |
| CIV-004 | normal | — | — | pendente |
| CIV-005 | normal | — | — | pendente |
| CIV-006 | fronteira | — | — | pendente |
| CIV-007 | fronteira | — | — | pendente |
| CIV-008 | fronteira | — | — | pendente |
| CIV-009 | fronteira | — | — | pendente |
| CIV-010 | fronteira | — | — | pendente |
| CIV-011 | excecao | — | — | pendente |
| CIV-012 | excecao | — | — | pendente |
| CIV-013 | excecao | — | — | pendente |
| CIV-014 | excecao | — | — | pendente |
| CIV-015 | excecao | — | — | pendente |

## Penal — 15

| ID | Cenário | Curadoria | Revisão | Status |
|---|---|---|---|---|
| PEN-001 | normal | — | — | pendente |
| PEN-002 | normal | — | — | pendente |
| PEN-003 | normal | — | — | pendente |
| PEN-004 | normal | — | — | pendente |
| PEN-005 | normal | — | — | pendente |
| PEN-006 | fronteira | — | — | pendente |
| PEN-007 | fronteira | — | — | pendente |
| PEN-008 | fronteira | — | — | pendente |
| PEN-009 | fronteira | — | — | pendente |
| PEN-010 | fronteira | — | — | pendente |
| PEN-011 | excecao | — | — | pendente |
| PEN-012 | excecao | — | — | pendente |
| PEN-013 | excecao | — | — | pendente |
| PEN-014 | excecao | — | — | pendente |
| PEN-015 | excecao | — | — | pendente |

## Tributário — 15

| ID | Cenário | Curadoria | Revisão | Status |
|---|---|---|---|---|
| TRI-001 | normal | — | — | pendente |
| TRI-002 | normal | — | — | pendente |
| TRI-003 | normal | — | — | pendente |
| TRI-004 | normal | — | — | pendente |
| TRI-005 | normal | — | — | pendente |
| TRI-006 | fronteira | — | — | pendente |
| TRI-007 | fronteira | — | — | pendente |
| TRI-008 | fronteira | — | — | pendente |
| TRI-009 | fronteira | — | — | pendente |
| TRI-010 | fronteira | — | — | pendente |
| TRI-011 | excecao | — | — | pendente |
| TRI-012 | excecao | — | — | pendente |
| TRI-013 | excecao | — | — | pendente |
| TRI-014 | excecao | — | — | pendente |
| TRI-015 | excecao | — | — | pendente |

## Checklist de conclusão do programa

- [ ] 75/75 casos versionados e validados;
- [ ] 15 consumidor;
- [ ] 15 trabalhista;
- [ ] 15 cível;
- [ ] 15 penal;
- [ ] 15 tributário;
- [ ] 5 normal + 5 fronteira + 5 exceção por área;
- [ ] zero PII detectada pelo sanitizer;
- [ ] zero fonte fictícia/placeholder;
- [ ] curador != revisor em todos os casos;
- [ ] fontes oficiais e vigência conferidas;
- [ ] `EJC Legal Quality Certification` verde.