# Decisão — `CITACOES_MODO_ESTRITO` permanece DESLIGADO

**Data:** 2026-07-29 · **Escopo:** gate anti-alucinação de citações (`services/citation_gate.py`)

## A decisão

`CITACOES_MODO_ESTRITO=false` em produção, até que a medição descrita abaixo
mostre impacto ≤ 2% das respostas. Não é indefinição: é uma condição objetiva,
verificável por comando, com um responsável por virar a chave quando ela for
satisfeita.

## Por que não ligar agora

O modo estrito escala de aviso para **bloqueio** dois casos:

| Situação | Sem modo estrito | Com modo estrito |
|---|---|---|
| Súmula/artigo citado, **ausente** da base curada (`identificada`) | alerta ao revisor | **bloqueia** |
| Súmula/artigo achado só em versão **superada** (`possivelmente_desatualizada`) | alerta + revisão obrigatória | **bloqueia** |

A regra está certa. O problema é o denominador: "ausente da base curada" hoje
significa as duas coisas ao mesmo tempo — *a IA inventou* e *a norma é real mas
ainda não foi ingerida*. O gate não sabe distinguir. Ligar antes de a base
cobrir o repertório do escritório barra peça legítima, e o custo real disso não
é o retrabalho — é o advogado aprender a ignorar o alerta. Um gate em que
ninguém confia é pior que gate nenhum, porque dá a sensação de proteção.

O estado atual **não é permissivo**: `possivelmente_desatualizada` já pesa 0 no
score e já dispara `revisao_obrigatoria`. Nada passa silenciosamente — o que
muda com o modo estrito é apenas quem tem a palavra final, o revisor ou o gate.

## Como decidir (o número que falta)

Não existe hoje coluna que registre o status das citações; `ai_logs` guarda a
resposta, não o relatório do verificador. Por isso a medição é feita
reprocessando as respostas já geradas:

```bash
docker exec -i ejc_backend python - < scripts/medir_impacto_modo_estrito.py
```

O script reverifica as citações das respostas dos últimos 90 dias e compara os
bloqueantes com o modo estrito desligado e ligado. O delta é exatamente o que
passaria a barrar. Também roda automaticamente (informativo, sem derrubar o
job) no workflow **Produção — prova de continuidade**.

Leitura do resultado:

- **`proporcao_afetada` ≤ 0,02** → ligar. A base curada cobre o que a IA cita.
- **acima disso** → manter desligado e **primeiro ingerir** o que aparece em
  `citacoes_distintas_que_bloqueariam`. Essa lista é o mapa das lacunas da base:
  cada entrada é uma súmula ou artigo que o escritório usa e o RAG não conhece.
  A contagem é por citação distinta de propósito — quarenta ocorrências do mesmo
  artigo são um buraco, não quarenta problemas.

## Quando virar a chave

```bash
# .env de produção
CITACOES_MODO_ESTRITO=true
```

Reinício do backend basta (a flag é lida por `get_settings()`, com cache).
Confirme depois com a sonda de flags:

```bash
docker exec -i ejc_backend python - < scripts/check_flags_producao.py
```

Se depois de ligar aparecer bloqueio em peça legítima, o caminho é **ingerir a
norma faltante**, não desligar o modo — desligar devolve o sistema ao ponto de
partida e perde o sinal que o bloqueio deu.

## Referências

- `backend/app/services/citation_gate.py` — `avaliar_bloqueantes(relatorio, modo_estrito=…)`
- `backend/app/services/verificador_jurisprudencia.py` — estados das citações
- `.env.example` (bloco de IA) — descrição da flag
- `docs/ai/EJC_AI_HITL_POLICY.md` — revisão humana obrigatória
