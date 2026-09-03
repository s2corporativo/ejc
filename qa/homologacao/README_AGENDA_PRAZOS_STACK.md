# Agenda/Prazos — referência de homologação

Para a cadeia #1343 → #1344 → #1345 → #1346 → #1347, usar em conjunto:

- `qa/homologacao/matriz_homologacao.json` — matriz geral;
- `qa/homologacao/run_homologacao.py` — executor autenticado existente;
- `qa/homologacao/H06_AGENDA_PRAZOS_EXECUCAO.md` — prova específica ampliada;
- `qa/homologacao/h06_agenda_prazos_validate.py` — guarda estática, sem rede.

A guarda estática não comprova ambiente, RBAC real, notificações reais ou experiência humana. #381/#1209 permanecem dependentes de execução autenticada e aceite humano.
