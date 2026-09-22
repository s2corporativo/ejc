# Curadoria real do gold set jurídico do EJC

## Regra de integridade

A fila de curadoria contém 75 slots de cobertura. Ela não é um gold set e não pode ser usada para medir qualidade. Um slot só pode ser marcado como `aprovado` depois que um caso real, pseudonimizado e juridicamente conferido estiver em um arquivo `gold_set*.jsonl` e passar pelo `gold_governance`.

É proibido preencher um slot com caso inventado, texto gerado pela IA, jurisprudência fictícia, placeholder ou referência cuja vigência não tenha sido conferida. A ferramenta de fila não cria fatos, teses, gabaritos, fontes ou atestações.

## Matriz mínima

A versão 1.0 exige 75 casos: cinco áreas (`consumidor`, `trabalhista`, `civel`, `penal` e `tributario`), três cenários (`normal`, `fronteira` e `excecao`) e cinco casos por combinação de área e cenário.

Enquanto os casos reais não são recebidos, o repositório mantém um benchmark separado em `benchmarks/rag_source_curated.jsonl`. Ele contém 14 fichas da Biblioteca Jurídica com URL oficial, snapshot local, data de verificação e `gerado_por_IA=false`. Esse benchmark mede recuperação de fontes já versionadas; ele não mede qualidade de uma tese, não representa casos reais e não satisfaz o gate de gold humano.

| Área | Normal | Fronteira | Exceção | Total |
|---|---:|---:|---:|---:|
| Consumidor | 5 | 5 | 5 | 15 |
| Trabalhista | 5 | 5 | 5 | 15 |
| Cível | 5 | 5 | 5 | 15 |
| Penal | 5 | 5 | 5 | 15 |
| Tributário | 5 | 5 | 5 | 15 |
| **Total** | **25** | **25** | **25** | **75** |

## Fluxo obrigatório de cada slot

1. O responsável seleciona um caso real do acervo autorizado do escritório.
2. O caso é pseudonimizado antes de ser salvo no repositório ou enviado a qualquer serviço externo.
3. O responsável registra fatos, questão, resposta esperada, fontes oficiais e limitações.
4. Cada fonte recebe URL HTTPS oficial, identificador de versão ou hash do snapshot, data de consulta e status de vigência.
5. O curador jurídico registra sua identidade funcional e as datas de revisão e de conferência de vigência.
6. Um revisor independente confere o item quando houver disponibilidade. Se o próprio curador fizer a segunda conferência, isso deve ser declarado.
7. O caso entra no JSONL real, sem o campo `ficticio` igual a `true` e sem placeholders.
8. O gate técnico é executado:

```bash
cd backend
python -m app.eval.gold_governance --require-real \
  --dir app/eval \
  --areas consumidor,trabalhista,civel,penal,tributario \
  --min-casos-area 15 \
  --min-total 75 \
  --cenarios normal,fronteira,excecao \
  --min-casos-cenario 25
```

9. O slot da fila recebe `status: "aprovado"` e o `caso_id` correspondente somente após o gate verde.

## Benchmark de recuperação disponível agora

Para rodar o benchmark de fonte contra a infraestrutura RAG:

```bash
cd backend
python -m app.eval.run_eval \
  --gold app/eval/benchmarks/rag_source_curated.jsonl \
  --k 6 \
  --out /tmp/rag-source-baseline.json
```

Se o banco, os embeddings ou o modelo local estiverem indisponíveis, o comando deve ser tratado como **falha operacional**, mesmo que o processo termine sem exceção. Um resultado com `recall=0` por erro de infraestrutura não é uma medida de qualidade jurídica.

## Comandos da fila

Criar a fila inicial, sem sobrescrever uma fila existente:

```bash
cd backend
python -m app.eval.curation_queue init
```

Validar a matriz e os estados:

```bash
python -m app.eval.curation_queue check
```

Exibir o andamento:

```bash
python -m app.eval.curation_queue summary
```

## Estados permitidos

- `pendente`: slot ainda não atribuído.
- `em_curadoria`: caso selecionado e em preparação.
- `em_revisao`: caso preparado, aguardando conferência jurídica.
- `aprovado`: caso real correspondente passou pelo gate técnico e foi atestado.
- `bloqueado`: não pode ser usado até resolver privacidade, proveniência, vigência ou qualidade.

## O que deve ser entregue pelo escritório

Para realizar a curadoria real, o responsável jurídico precisa fornecer, por canal autorizado, os casos ou peças que podem ser usados, a identificação funcional dos curadores, a autorização de uso e as fontes oficiais conferidas. Sem esse material, o sistema deve permanecer com slots pendentes; preencher os 75 itens com exemplos seria uma falsificação da certificação.
