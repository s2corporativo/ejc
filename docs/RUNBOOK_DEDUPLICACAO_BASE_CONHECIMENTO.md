# Deduplicar os grandes textos legais da base de conhecimento

**Para quem:** o titular, no VPS. O script é a ferramenta; a execução é ato humano.

## O problema que isto resolve

A auditoria de 2026-08-27 mediu a base de produção e encontrou o mesmo texto
legal ingerido várias vezes por caminhos diferentes:

| Texto | Cópias | Trechos somados |
|---|---|---|
| Código de Processo Civil | 6 | ~4.230 |
| CLT | 4 | ~3.449 |
| Código Civil | 4 | ~3.307 |
| Constituição Federal | 4 | ~2.966 |
| Código de Processo Penal | 2 | ~1.393 |

O dedup nativo (`chave_origem` + `versao`/`vigente`, migration 068) não pegou
nada disso: ele só age quando a **mesma chave** é reingerida, e estas cópias
entraram por caminhos distintos — upload manual sem fonte × ingestão curada com
URL oficial.

**O prejuízo é de qualidade da resposta, não de espaço.** Quando o RAG busca um
artigo do CPC, recebe o mesmo artigo seis vezes, e as seis ocupam as vagas do
contexto enviado ao modelo — empurrando para fora a jurisprudência e a doutrina
que completariam a resposta. Como efeito colateral, rebaixar as redundantes
tira ~21% dos trechos da fila de indexação.

## O que o script faz — e o que ele nunca faz

**Rebaixa, não apaga.** A cópia perdedora recebe `vigente = false`, que é o
mecanismo que o próprio modelo já usa para versão superada (ver
`app/models/rag.py`). Consequências:

- sai do retrieval (`_FILTRO_VIGENTE_RAG` em `ai_service.py`)
- sai da fila de reindexação (`_SQL_DOCS_COM_ORFAO`)
- **os chunks permanecem intactos** — se uma petição já protocolada citou
  aquela cópia, a citação continua rastreável
- desfazer é um `UPDATE` (`--reverter`)

**Nunca toca no que não reconhece.** Só agrupa documentos que casam com um
`CANONICO` declarado no código — por número de lei (sinal forte) ou por apelido
explícito. Documento sem match é listado e **jamais** rebaixado. Por isso o Vade
Mecum, os modelos da Bíblia EJC e qualquer texto não previsto ficam intocados.

**Nunca toca em material de cliente.** A consulta filtra `client_id IS NULL` e
`categoria = 'legislacao'`.

## Qual cópia fica

Critério declarado em código (`pontuar`), do mais para o menos decisivo:

1. **revisado por humano** — alguém conferiu que o texto está correto
2. **tem fonte oficial** — dá para auditar de onde veio
3. veio de ingestão estruturada (`chave_origem`)
4. atualizado mais recentemente
5. versão maior
6. mais trechos (texto mais completo)

Repare que **procedência ganha de volume**: a cópia curada de 670 trechos vence
o upload manual de 1.006. É deliberado — texto maior pode ser texto sujo.

Empate total é resolvido pelo `id`, para a decisão ser determinística.

## Execução

### 1. Backup (obrigatório)

```bash
cd /opt/ejc && bash scripts/backup.sh
```

Ou confirme que o backup diário rodou: `GET /admin/backup/status`.

### 2. Simulação — não altera nada

```bash
docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento
```

Sai um relatório por grupo: qual cópia fica (`MANTER`), quais saem
(`rebaixar`), com fonte/revisado/nº de trechos de cada uma, e o total de
trechos que deixam a fila.

**Leia esse relatório.** Se alguma linha `MANTER` parecer a cópia errada, pare
e ajuste antes — o critério está em `pontuar()` e é revisável.

### 3. Aplicar

```bash
docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento --aplicar
```

Pede confirmação digitada (`DEDUPLICAR`). Sem isso, aborta sem alterar nada.

### 4. Conferir

```bash
docker exec ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT count(*) FILTER (WHERE embedding IS NULL) AS faltam FROM knowledge_chunks;"
```

O número deve ter caído. E o rebaixamento fica registrado em `extra`:

```bash
docker exec ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT left(titulo,50), extra->>'deduplicado_em', extra->>'duplicata_de'
     FROM knowledge_docs WHERE extra ? 'deduplicado_em' ORDER BY 1;"
```

### 5. Desfazer, se necessário

```bash
docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento --reverter
```

Devolve `vigente = true` a tudo que **este script** marcou — não afeta
documentos rebaixados por outros motivos (versionamento legítimo).

## Depois da deduplicação

Rebaixar tira as cópias da fila, mas **não reindexa o que ficou**. Se a
indexação já tiver passado por aquele documento, nada muda; se ainda não,
ele entra normalmente. Para forçar:

```bash
docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos
```

## O que este script NÃO resolve

- **Cobertura por área** — quantas áreas do direito têm fonte curada. Isso já
  existe no sistema: `GET /ia-governanca/rag-curadoria` e a tela
  *Conhecimento Governado* (Workspace de Inteligência). Use o que está lá.
- **Compilações** — o "VADE MECUM 2026" (5.103 trechos) repete todos os códigos,
  mas não casa com nenhum canônico e por isso não é tocado. Decidir se ele fica
  é curadoria, não automação.
- **Categoria errada** — a cópia intitulada "CPP" está como `peca_escritorio`
  (categoria restrita por cliente) em vez de `legislacao`, o que a torna
  irrecuperável pela busca. Como há quatro cópias corretas do CPP, o caminho é
  removê-la, não recategorizá-la — mas isso é decisão sua, não do script.

## Ampliar o alcance

Cobrir mais textos = acrescentar um `Canonico` em
`scripts/deduplicar_base_conhecimento.py`, com número da lei e apelidos. Todo
`Canonico` novo deve vir com teste de colisão em
`tests/test_deduplicar_base_conhecimento.py` — o risco real aqui não é apagar
demais (o script não apaga), é **agrupar duas leis distintas** e tirar um
diploma inteiro do alcance da IA. Os testes existentes já cobrem os casos
traiçoeiros: CPP × CPP Militar, CPC × CPP, Código Civil × Processo Civil,
CPC/2015 × CPC/1973.
