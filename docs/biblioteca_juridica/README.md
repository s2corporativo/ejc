# Biblioteca Jurídica Inteligente — EJC

> **STATUS ATUAL: CORPUS EM QUARENTENA / NÃO HOMOLOGADO PARA FUNDAMENTAÇÃO AUTOMÁTICA.**
>
> A auditoria de segurança de 14/08/2026 revogou a homologação anterior do lote piloto. Os arquivos deste diretório são artefatos versionados de trabalho; a presença no GitHub **não** significa que uma tese, julgado ou metadado esteja juridicamente validado.

O lote piloto contém 24 documentos distribuídos por oito áreas. O registro `JUR-CONS-000016` foi reconstruído após a auditoria identificar referência simulada e metadados incorretos na versão anterior. Os demais registros permanecem pendentes de revalidação individual.

## Regra de autoridade

A cadeia operacional do EJC é:

**fonte oficial validada → precedente validado → tese derivada → bloco argumentativo → pedido → modelo → texto gerado por IA.**

Documentos derivados, modelos e textos de IA não criam autoridade jurídica por repetição ou similaridade.

## Estrutura

```text
docs/biblioteca_juridica/
├── README.md
├── RELATORIO_AUDITORIA_LOTE_PILOTO.md
├── GUIA_EXECUCAO_PRODUCAO.md
├── grafico_relacoes.yaml
└── {area}/
    └── NN_tema.md
```

O `grafico_relacoes.yaml` descreve relações conceituais. Relação de grafo não eleva a autoridade de nenhum nó e só pode ser usada operacionalmente quando os documentos relacionados estiverem aprovados no RAG.

## Metadados canônicos mínimos

| Chave | Regra |
|---|---|
| `tipo_camada` | `fonte_primaria`, `jurisprudencia_estruturada`, `tese_juridica`, `bloco_argumentativo`, `pedido_juridico` ou `modelo_peca` |
| `canonical_id` | identificador único e estável |
| `origem_conteudo` | origem real do conteúdo; nunca promover IA/modelo a fonte oficial |
| `autoridade_juridica` | normativa, vinculante, jurisprudencial, persuasiva, doutrinária, analítica ou sem autoridade |
| `score_autoridade` | 0–100; modelo de IA deve permanecer em 0 |
| `area_juridica` | área canônica do lote |
| `nivel_confiaca` | ALTA, MEDIA ou BAIXA; confiança não substitui fonte |
| `data_pesquisa` | data da pesquisa/verificação |
| `gerado_por_IA` | identifica conteúdo gerado por IA |
| `fontes_utilizadas` | obrigatório para teses, argumentos e pedidos derivados |

Jurisprudência de confiança ALTA deve possuir fonte institucional rastreável e data de verificação. Conteúdo de autoridade não pode conter processo, precedente ou URL simulados.

## Validação local segura

A validação deve ser feita explicitamente sobre este diretório:

```bash
python3 backend/scripts/ingestao_biblioteca_juridica.py \
  --dir docs/biblioteca_juridica \
  --graph docs/biblioteca_juridica/grafico_relacoes.yaml
```

**Resultado esperado enquanto houver registros não saneados:** saída `BLOQUEADO` e código diferente de zero. Isso é comportamento correto, não defeito.

O modo `--execute` não deve ser utilizado enquanto o lote não passar integralmente pela validação e pela revisão humana. Mesmo quando executado, o script grava os documentos como `rag_status=pendente`; ele não concede aprovação automática.

## Quarentena de versões eventualmente já ingeridas

Após o hardening ser implantado, o script `backend/scripts/quarentenar_biblioteca_juridica_piloto.py` deve ser usado primeiro em dry-run e, somente após conferir os IDs, em `--execute`. Ele preserva documentos, chunks, embeddings, histórico e recusas humanas; apenas retira o lote da base ativa até revalidação.

Consulte `GUIA_EXECUCAO_PRODUCAO.md` para a sequência operacional completa.

## Estado do lote piloto

| Indicador | Estado |
|---|---|
| Arquivos canônicos | 24 |
| Homologação jurídica do conjunto | **REVOGADA** |
| Documentos liberados automaticamente por este diretório | **0** |
| JUR-CONS-000016 | corrigido com Tema 466/STJ e Súmula 479/STJ; ainda sujeito à curadoria |
| Demais 23 registros | pendentes de revalidação individual |
