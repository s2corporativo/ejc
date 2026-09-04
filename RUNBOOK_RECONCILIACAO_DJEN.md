# RUNBOOK — Reconciliação da captura DJEN por amostragem independente

Issue [#572](https://github.com/s2corporativo/ejc/issues/572) (Auditoria Técnica Parte 9,
item P8). Origem do problema: `GET /intimacoes/status-captura` informa que o job de captura
executou com sucesso e devolveu zero intimações — mas sucesso de execução não prova
completude de captura. Uma falha silenciosa da API Comunica/DJEN (mudança de contrato,
filtro incorreto, OAB mal configurada, paginação truncada) passa exatamente com a mesma cara
de "nenhuma intimação hoje". Só comparar o que o EJC capturou com a fonte oficial (portal
DJEN/CNJ) detecta essa classe de falha — é a mesma lição já registrada em `CLAUDE.md`:
"Monitoramento afere execução, não resultado."

**Este runbook prepara a reconciliação. Não a substitui.** A consulta oficial com inscrição
real de OAB e a validação operacional exigem responsável humano autorizado — ver "Limite de
autonomia" na Issue. Nenhum agente de IA certifica sozinho que a captura DJEN está completa.

## Pré-requisito: cadastrar a OAB monitorada

A reconciliação real só é possível depois que os advogados monitorados tiverem
`users.djen_oab_numero` / `users.djen_oab_uf` cadastrados (Bloco 6 do
`docs/auditoria/plano-lancamento-v3.md`). Sem OAB cadastrada, não há o que amostrar: o
job de captura (`services/scheduler.py`, job `djen_intimacoes`) seleciona apenas
advogado com `djen_oab_numero` preenchido.

Dois caminhos, ambos válidos:

1. **Pela interface** — menu do avatar → *Minha OAB (intimações DJEN)*. O modal já abre
   com o valor gravado; desligar o monitoramento é um botão separado e explícito.
2. **Em lote, pelo terminal** — `backend/scripts/configurar_oab_djen.py`, dry-run por
   padrão:

   ```bash
   # conferir de quem o job vai capturar hoje (somente leitura)
   docker exec -it ejc_backend python -m scripts.configurar_oab_djen --verificar

   # simular; depois repetir com --aplicar (pede confirmação digitada)
   docker exec -it ejc_backend python -m scripts.configurar_oab_djen \
       --definir "<e-mail ou fragmento do nome>=<numero>/<UF>"
   ```

   O script recusa agir quando o identificador casa zero ou mais de um usuário, quando a
   OAB já pertence a outro usuário, ou quando diverge da OAB do perfil — e grava
   `AuditLog` por alteração. Um erro em qualquer definição aborta o lote inteiro: meio
   cadastro aplicado é pior que nenhum, porque parece configurado.

### A API do Comunica/CNJ é geograficamente restrita

`https://comunicaapi.pje.jus.br` fica atrás de uma distribuição CloudFront com
restrição por país. De fora do Brasil ela devolve **403 em qualquer rota**, inclusive
`/swagger`, com o corpo *"The Amazon CloudFront distribution is configured to block
access from your country"* — verificado em 04/09/2026 a partir de um egress nos EUA
(`x-amz-cf-pop: IAD55`), enquanto BrasilAPI respondia 200 e DataJud 401 pelo mesmo
túnel, o que descarta bloqueio genérico a serviços brasileiros.

Consequência prática: **cadastro de OAB correto não garante captura**. Se o servidor
que roda o job não sair do Brasil, todas as consultas viram `http_4xx` e o advogado
fica sem intimação — o heartbeat marca `erro`, mas nada no texto diz que a causa é a
localização do servidor.

Confirme no host onde o job roda (um comando, sem cadastro nenhum):

```bash
docker exec -it ejc_backend python -m scripts.configurar_oab_djen --testar-fonte
# ou, cru:
curl -s -o /dev/null -w '%{http_code}\n' https://comunicaapi.pje.jus.br/swagger
```

`200` = a fonte fala com este servidor. `403` = não fala, e nenhum ajuste de cadastro
resolve; a saída precisa ser por egress brasileiro (proxy/servidor no país), decisão
de infraestrutura do titular.

**Como o cadastro errado se manifesta:** o `heartbeat` do job classifica o resultado, não
a execução. Zero OAB cadastrada devolve `nenhuma_oab_configurada` com status `erro`; par
número/UF incompleto devolve `oab_nao_configurada` para aquele advogado. Um painel "verde"
com `resultado: sucesso_sem_resultados` significa que a fonte respondeu e não havia
publicação — que é diferente de não ter perguntado.

## Periodicidade e amostra sugeridas

- **Cadência da amostragem:** semanal, numa segunda-feira útil, cobrindo a semana anterior.
  Alinhado à cadência do próprio job (diário, 06h30) sem exigir checagem diária manual — o
  heartbeat (`GET /intimacoes/status-captura`) já cobre a detecção de job que parou de rodar;
  este runbook cobre o job que roda e captura errado ou incompleto.
- **Amostra:** rotação por OAB monitorada. Com poucas OABs cadastradas (fase inicial pós
  Bloco 6), reconcilie todas a cada ciclo. Se o número de OABs monitoradas crescer o
  suficiente para tornar isso caro, mova para amostragem aleatória de N OABs por ciclo
  (sugestão: no mínimo 3 ou 20% do total monitorado, o que for maior), garantindo que toda
  OAB monitorada seja reconciliada pelo menos uma vez por mês.
- **Gatilho fora do calendário:** qualquer suspeita concreta — pico ou queda abrupta na
  contagem diária, mudança de comportamento reportada por advogado, ou alteração no
  `services/djen_service.py` / `services/ingestors/djen.py` / contrato da API Comunica —
  dispara reconciliação imediata da(s) OAB(s) afetada(s), fora da rotação.

## Janela temporal

- **Janela padrão de comparação:** 7 dias corridos, terminando na data da checagem
  (ex.: checagem na segunda-feira compara segunda a segunda anterior).
- **Por quê 7 dias e não 1:** a API Comunica pode publicar uma comunicação com atraso em
  relação à data de disponibilização real; uma janela de 1 dia teria falsos positivos de
  "faltou" por comunicação ainda não propagada na fonte. 7 dias absorve esse atraso comum
  sem esconder uma lacuna real.
- **Janela estendida (investigação):** ao confirmar divergência, amplie para 30 dias antes de
  abrir o incidente, para medir o tamanho real do problema (evento pontual x degradação
  contínua).

## Procedimento

1. **Levantar a amostra do EJC (read-only, sem tocar no DJEN):**
   ```bash
   docker exec -it ejc_backend python -m scripts.reconciliar_djen_amostra \
       --oab-numero <numero> --oab-uf <uf> --dias 7
   ```
   Devolve: contagem capturada pelo EJC na janela, lista de identificadores
   (`comunicacao_id_externo`, `numero_processo`, tribunal, tipo, data — nenhum conteúdo de
   intimação) e um bloco de evidência já formatado, com a OAB mascarada, pronto para
   preencher e colar no registro (ver `backend/scripts/reconciliar_djen_amostra.py`).
   Rodar `--formato json` se a listagem completa precisar ser processada por outro script.

2. **Consultar a fonte oficial (ato humano, responsável autorizado):**
   Acessar o portal Comunica (`https://comunica.pje.jus.br`) ou a interface oficial
   equivalente do CNJ, buscar pela mesma OAB e mesma janela temporal (7 dias), e anotar:
   contagem total de comunicações no período e, se o portal expuser, os identificadores/
   números de processo — o suficiente para comparar com a saída do passo 1.
   **Só pode ser feito por operador humano com inscrição OAB autorizada.** Não há caminho
   automatizado aqui — nem é objetivo deste runbook criar um.

3. **Comparar:**
   - Contagem oficial == contagem EJC **e** nenhum identificador presente em um lado e
     ausente no outro → reconciliação OK, sem ação.
   - Qualquer divergência (contagem diferente OU identificador presente na fonte oficial e
     ausente no EJC OU vice-versa) → segue para "Divergência e escalonamento" abaixo.

4. **Registrar evidência minimizada** (nunca o conteúdo da intimação nem dado pessoal do
   processo — só o necessário para auditar a checagem em si):

   | Campo | Conteúdo |
   |---|---|
   | `data_checagem` | data em que a reconciliação foi feita |
   | `janela` | data início – data fim comparadas |
   | `oab_mascarada` | ex.: `1****6/MG` (nunca o número completo em log/Issue) |
   | `identificador_interno` | `advogado_id` do EJC (não expõe a OAB) |
   | `contagem_ejc` | número devolvido pelo script |
   | `contagem_oficial` | número visto no portal DJEN/CNJ |
   | `divergencia` | `contagem_oficial - contagem_ejc` (0 = sem divergência) |
   | `responsavel` | quem executou a consulta manual |
   | `acao` | nenhuma / incidente aberto (`#NNN`) / escalonado |

   Guardar esse registro em local já adequado a evidência operacional (ex.: comentário na
   Issue de acompanhamento do ciclo de reconciliação, ou planilha interna do escritório —
   **nunca** em log de aplicação nem em repositório público). O bloco impresso pelo script
   no passo 1 já vem no formato acima, faltando preencher `contagem_oficial`, `divergencia`,
   `responsavel` e `acao`.

## Limiar de alerta

- **Divergência de contagem:** qualquer `divergencia != 0` na janela de 7 dias é reportável.
  Não existe tolerância "razoável" aqui — captura de intimação é prazo processual; uma
  intimação perdida tem custo desproporcional ao esforço de checar.
- **Identificador ausente no EJC:** dispara alerta mesmo com contagem total batendo por
  coincidência (ex.: uma capturada a mais em outro dia mascarando uma perdida). Reporte
  contagem E identificadores, nunca só a contagem.
- **Divergência recorrente:** a mesma OAB com divergência em 2 ciclos seguidos eleva a
  severidade automaticamente (ver escalonamento) — indício de degradação persistente, não
  de atraso pontual de propagação da fonte.

## Divergência e escalonamento

1. **Abrir incidente próprio** — Issue nova no repositório, rotulada para achado operacional
   (não reaproveitar a Issue #572, que é sobre o ferramental). Conteúdo mínimo: OAB mascarada,
   janela, contagens, identificadores ausentes (só o identificador — sem texto da intimação),
   responsável pela checagem.
2. **Preservar evidência** antes de qualquer nova execução do job de captura que possa
   sobrescrever o estado observado — print/anotação do portal oficial e a saída do script
   (passo 1) datados e anexados ao incidente.
3. **Não alterar prazo algum automaticamente.** Este runbook e o script associado são
   estritamente read-only. Se a divergência indicar prazo processual em risco, o alerta segue
   para revisão humana imediata do advogado responsável pelo caso — nunca para criação
   automática de prazo a partir da reconciliação.
4. **Investigar a causa técnica** só depois de preservada a evidência: contrato da API Comunica
   mudou, OAB mal cadastrada, paginação/filtro no `services/djen_service.py`, job parado
   silenciosamente (conferir heartbeat em paralelo), rate limit da fonte. Vira tarefa de
   correção separada, com Issue própria referenciando o incidente.
5. **Divergência recorrente (2+ ciclos)** — eleva para revisão do titular antes do próximo
   ciclo de captura automática daquela OAB, independentemente da causa já ter sido
   identificada ou não.

## Como o resultado "zero" é validado

"Zero intimações" só é aceito como correto quando a reconciliação deste runbook (ou uma
reconciliação equivalente já registrada para aquele advogado/janela) também encontrou zero na
fonte oficial. Fora do ciclo de reconciliação, um "zero" isolado do
`GET /intimacoes/status-captura` prova apenas que o job rodou — não que não havia nada para
capturar. Isso é, por desenho, uma lacuna que só a amostragem periódica fecha; não existe
correção de código que a elimine sozinha, porque o problema é a ausência de uma fonte de
verdade paralela, não um bug pontual.

## Limite de autonomia (herdado da Issue #572)

- Consulta oficial ao DJEN/CNJ com inscrição OAB real: **sempre humana**, nunca automatizada
  por este ou qualquer outro script do EJC.
- Nenhum agente de IA declara a captura DJEN "reconciliada" ou "completa" a partir apenas da
  execução deste script — o script só prepara o lado EJC da comparação.
- A primeira reconciliação de fato (passo 2 em diante) e o cadastro real das OABs monitoradas
  (Bloco 6 do plano de lançamento) são ações pendentes do titular/operador autorizado, fora do
  escopo do PR que introduziu este runbook.

## Ferramental

- `backend/scripts/configurar_oab_djen.py` — CLI de cadastro/conferência da OAB
  monitorada (`--verificar` é read-only; a gravação exige `--aplicar` + confirmação
  digitada). Ver a seção *Pré-requisito* acima.
- `backend/scripts/reconciliar_djen_amostra.py` — CLI read-only, só lê `djen_comunicacoes`
  filtrado por OAB (via `users.djen_oab_numero/uf`) e janela; nunca acessa o DJEN/CNJ. Ver
  cabeçalho do arquivo para os comandos de execução.
- `GET /intimacoes/status-captura` — heartbeat de execução do job (já existente); use em
  conjunto, não no lugar deste runbook.
