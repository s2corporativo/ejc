# Guia de curadoria do gold set — De Paula Teixeira Advogados

O **gold set** é o ativo mais valioso da avaliação de IA do EJC: é a régua que transforma
"achamos que melhorou" em número. Só o escritório pode produzi-lo — este guia é o passo a
passo para isso, sem que ninguém precise mexer em código.

> **Regra de ouro:** nunca invente jurisprudência e nunca grave PII real. Tudo abaixo existe
> para garantir essas duas coisas.

---

## O que você vai produzir

Dois arquivos (um por tipo de avaliação — comece pelo primeiro):

| Arquivo | Avalia | Template |
|---|---|---|
| `gold_set.jsonl` | **Retrieval (RAG)** — a busca traz as fontes certas? | `gold_set.template.json` |
| `gold_set_pecas.jsonl` | **Geração de peças** — a peça sustenta as teses e não alucina? | `gold_set_pecas.template.json` |

Cada arquivo é **JSONL**: uma linha = um caso, cada linha é um JSON completo no formato do
template. Nada de vírgula entre linhas nem colchete em volta.

**Meta:** 50–150 casos reais por arquivo, cobrindo as áreas de atuação **proporcionalmente ao
volume real** do escritório. Não precisa chegar lá de uma vez — ver "Comece pequeno".

---

## Comece pequeno (1 tarde de trabalho)

1. Escolha as **2–3 áreas de maior volume** (ex.: trabalhista, consumidor, cível).
2. Para cada área, escreva **5–7 perguntas jurídicas reais** que clientes/advogados fazem —
   as mais recorrentes. Isso já dá 15–20 casos: suficiente para o primeiro baseline.
3. Preencha um caso por linha seguindo o template. Rode o smoke (abaixo) para validar o formato.
4. Cresça a partir daí, uma área por vez.

---

## Como preencher UM caso de RAG (`gold_set.jsonl`)

Campos completos em `gold_set.template.json`. O essencial:

- **`id`** — único e estável (ex.: `trab-001`). Não reaproveite id.
- **`area`** — trabalhista | consumidor | civel | previdenciario | tributario | familia | empresarial.
- **`query`** — a **pergunta jurídica**, do jeito que seria feita ao sistema. É a pergunta, não
  os dados do caso. Ex.: *"prazo prescricional para reclamar verbas rescisórias na Justiça do
  Trabalho"*.
- **`expected_titulos`** — os títulos dos documentos da base que a busca **deveria** trazer.
  Casa por trecho (substring, sem acento): `"CLT art. 11"` casa com *"CLT - Art. 11
  (Prescrição)"*. Liste 1 a 3 âncoras fortes.
- **`expected_citacoes`** (opcional) — as citações que uma boa resposta conteria, **conferidas
  na fonte oficial**. Usadas para medir alucinação no modo `--full`.

---

## Como preencher UM caso de PEÇA (`gold_set_pecas.jsonl`)

Campos completos em `gold_set_pecas.template.json`. O essencial:

- **`fatos`** — a narrativa do caso **pseudonimizada** (ver checklist). Use marcadores:
  `[CLIENTE_1]`, `[EMPRESA_1]`, `[PARTE_CONTRARIA_1]`.
- **`tipo_peca_esperado`** — uma chave válida de tipo de peça (lista abaixo).
- **`teses_esperadas`** — as teses que a peça gerada **deve** sustentar.
- **`jurisprudencia_esperada`** (opcional) — súmulas/julgados **reais e conferidos**. Se não
  tiver certeza, **deixe de fora** — melhor vazio que inventado.
- **`criterios`** — critérios objetivos de aceitação (estrutura formal completa, fatos ancorados
  em prova, nenhuma citação reprovada no gate, pedidos cobertos).
- **`ficticio`** — `false` para caso real pseudonimizado.

### Tipos de peça válidos (`tipo_peca_esperado`)

`peticao_inicial` · `contestacao` · `replica` · `recurso_ordinario` · `apelacao` ·
`contrarrazoes` · `embargos_declaracao` · `agravo` · `cumprimento_sentenca` ·
`impugnacao_cumprimento` · `embargos_execucao` · `mandado_seguranca` · `memorias` · `acordo` ·
`parecer` · `notificacao` · `contrato` · `impugnacao` · `impugnacao_documentos` ·
`manifestacao_preliminares` · `especificacao_provas` · `alegacoes_finais` ·
`recurso_especial` · `recurso_extraordinario` · `resposta_notificacao`

---

## Checklist de pseudonimização (LGPD — obrigatório antes de gravar)

Antes de salvar qualquer caso real, troque por marcadores:

- [ ] Nomes de pessoas → `[CLIENTE_1]`, `[PARTE_CONTRARIA_1]`, `[TESTEMUNHA_1]`
- [ ] Nomes de empresas → `[EMPRESA_1]`
- [ ] CPF / CNPJ / RG → remover ou `[CPF]` / `[CNPJ]`
- [ ] Número de processo (CNJ) → remover se identificar o caso
- [ ] Endereços, e-mails, telefones → remover
- [ ] Valores exatos que identifiquem a parte → arredondar ou marcar `[VALOR]`

> O smoke roda um detector estrutural de PII nos casos reais e **falha** se achar CPF/CNPJ/
> e-mail/telefone etc. — mas ele não pega nome próprio. A responsabilidade de pseudonimizar o
> nome é do curador.

## Checklist anti-alucinação (conferência de fonte)

- [ ] Toda súmula/artigo/julgado listado foi **conferido na fonte oficial** (Planalto, sítio do
      tribunal, DJe)?
- [ ] Na dúvida sobre uma referência, ela ficou **de fora** (nunca "provavelmente é a Súmula X")?
- [ ] Nenhum placeholder `SUMULA-FICTICIA-XXX` sobrou num caso real (`ficticio: false`)?

---

## Validar o formato (sem banco, sem IA)

Dentro do backend (ou no VPS via `docker compose exec backend`):

```bash
python -m app.eval.run_eval --smoke
```

Ele checa **todos** os `*.jsonl` do pacote: JSON válido, campos obrigatórios presentes, ids não
duplicados, e detecta PII estrutural esquecida em casos reais. É o mesmo check que roda no CI —
verde aqui, verde lá.

## Medir (precisa do banco com a base de conhecimento)

```bash
# Só retrieval (rápido, determinístico)
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo: roda a IA, mede alucinação de citação + groundedness
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Comparar provedores lado a lado sobre o MESMO contexto
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge \
    --providers anthropic,maritaca --out comparacao.json

# Guardar baseline para comparar depois de uma mudança
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json
```

---

## Onde guardar o arquivo real

O `gold_set.jsonl`/`gold_set_pecas.jsonl` **real** contém casos do escritório (mesmo
pseudonimizados). Trate como material interno: mantenha-o no servidor/ambiente do escritório e
**não** versione conteúdo sensível sem decisão consciente. Os `*.example.jsonl` e `*.template.json`
versionados são só scaffold de formato (100% fictícios) — nunca copie a "jurisprudência" de
exemplo para o gold set real.

---

## Fluxo recomendado

1. **Baseline** — monte 15–20 casos e meça o pipeline atual.
2. **Compare provedores** — decisões de roteamento devem ser orientadas por métricas.
3. **Uma variável por vez** — reranker, FTS e embedding devem ser medidos separadamente.
4. **Cresça o gold set** — mais casos tornam a régua mais confiável.
