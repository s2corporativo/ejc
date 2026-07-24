# Adaptador de proveniência do RAG jurídico

## Objetivo

Converter os campos existentes de `knowledge_docs`, `extra` e chunks no contrato
canônico definido em `app.schemas.ai_proveniencia.ProvenienciaJuridica`.

Este módulo não cria outro enum, envelope ou regra de isolamento. As regras gerais
pertencem ao contrato canônico do PR #459; `rag_provenance.py` contém somente o
mapeamento específico do corpus RAG.

## Princípios

1. O adaptador não abre banco e não altera o ranking do retrieval.
2. `client_id` nunca é exposto.
3. `case_id` é validado pela camada canônica quando o chamador informa o caso esperado.
4. Página só é preenchida quando existe metadado real do chunk/documento.
5. `chunk_index` nunca é tratado como página.
6. `atualizado_em` é metadado do registro, não data do documento.
7. Fonte confirmada exige data de verificação.
8. Fonte oficial confirmada também exige estado de vigência.
9. Scores de retrieval são limitados ao intervalo `0..1` antes de preencher
   `confianca_extracao`.
10. A classificação de sigilo nunca pode ser menos restritiva que o escopo
    definido em `base_rag`.

## Estados de conferência

O adaptador utiliza diretamente `StatusConferenciaFonte`:

- `confirmada`;
- `pendente_conferencia`;
- `nao_localizada`;
- `possivelmente_desatualizada`;
- `identificacao_insuficiente`.

A ordem é fail-safe. Não vigência e fonte não localizada prevalecem sobre qualquer
marcação anterior de revisão.

## Confidencialidade derivada

O campo existente `knowledge_docs.base_rag` é a fonte mínima de classificação:

| `base_rag` | Confidencialidade mínima |
|---|---|
| `publica` | `publica` |
| `escritorio` | `interna` |
| `caso` | `confidencial` |

Quando `case_id` existe, a classificação mínima também é `confidencial`, mesmo em
registro legado sem `base_rag`. Uma classificação explícita em
`extra["proveniencia"]["nivel_confidencialidade"]` pode aumentar o sigilo para
`restrita` ou `segredo_justica`, mas nunca rebaixá-lo para `publica`.

Essa derivação não substitui autorização, RBAC, filtro por cliente/caso ou
segregação física/lógica do corpus.

## Mapeamento principal

| Origem RAG | Campo canônico |
|---|---|
| `knowledge_docs.id` | `documento_id` |
| `fonte`/`extra.proveniencia.url` | `url_oficial`, quando HTTP(S) |
| nome explícito ou caminho da fonte | `nome_arquivo` |
| metadado real do chunk | `pagina` |
| conteúdo recuperado | `trecho` |
| `case_id` | `case_id` |
| `base_rag` + sigilo explícito | `nivel_confidencialidade` |
| data explicitamente declarada | `data_documento` |
| data de revisão/conferência | `data_verificacao` |
| `versao` | `versao_documento` |
| `hash_conteudo` | `hash_fonte` |
| score do retrieval | `confianca_extracao` |

Campos específicos do RAG ficam em `metadados`, incluindo:

- `chunk_id`;
- `chunk_index`;
- `chave_origem`;
- `categoria`;
- `tribunal`;
- `base_rag`;
- `revisado`;
- `atualizado_em`;
- motivos da classificação.

## JSONB opcional

Metadados adicionais podem permanecer em `extra["proveniencia"]`, sem migration:

```json
{
  "proveniencia": {
    "tipo_fonte": "fonte_oficial",
    "nivel_confidencialidade": "publica",
    "nome_arquivo": "acordao.pdf",
    "pagina": 8,
    "data_documento": "2026-06-20",
    "data_verificacao": "2026-07-23T12:00:00-03:00",
    "processo_origem": "0000000-00.2026.8.13.0000",
    "url": "https://fonte-oficial.example/documento",
    "status_conferencia": "confirmada",
    "fonte_localizada": true
  }
}
```

## Integração

O retrieval rastreável deverá chamar:

```python
normalizar_proveniencia(
    doc=documento,
    chunk=resultado,
    case_id_esperado=case_id_autorizado,
)
```

O retorno é `ProvenienciaJuridica`. Consumidores HTTP devem serializar com
`model_dump(mode="json")` e jamais remover a revisão humana obrigatória.

## Banco e rollback

Não há migration. A promoção futura de campos JSONB para colunas somente será
considerada após uso real, necessidade comprovada de índice e plano de upgrade,
downgrade, teste com PostgreSQL/pgvector e rollback.
