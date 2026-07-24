# Contrato de proveniência do RAG jurídico

## Objetivo

Padronizar a origem de cada trecho utilizado pela IA sem criar novo banco,
serviço externo ou custo recorrente. A primeira fase reutiliza o JSONB
`knowledge_docs.extra` e os campos existentes de documento/chunk.

A proveniência não substitui autenticação, autorização, isolamento por caso ou
governança do RAG. Ela é uma camada de rastreabilidade aplicada depois que a
fonte já passou pelos filtros de escopo e confiança.

## Estados permitidos

| Estado | Significado operacional |
|---|---|
| `confirmada` | Documento aprovado, revisado ou conferido na base do EJC. |
| `pendente_conferencia` | Fonte identificada, mas ainda sem validação humana ou oficial suficiente. |
| `nao_localizada` | A origem declarada não foi encontrada. Não deve fundamentar uma peça. |
| `possivelmente_desatualizada` | Documento não vigente, revogado, superado ou marcado como desatualizado. |
| `identificacao_insuficiente` | Não há título, arquivo, URL ou chave de origem suficiente para auditoria. |

Os estados são fail-safe. Um documento não vigente ou não localizado não pode
ser promovido a `confirmada` apenas porque foi revisado anteriormente.

## Shape canônico

```json
{
  "documento_id": "uuid",
  "chunk_id": "uuid",
  "chunk_index": 3,
  "nome_arquivo": "contestacao.docx",
  "pagina": 12,
  "trecho": "Trecho efetivamente utilizado...",
  "fonte": "URL ou referência",
  "chave_origem": "identidade estável da ingestão",
  "processo_origem": "0000000-00.2026.8.13.0000",
  "case_id": "uuid",
  "data_documento": "2026-07-01",
  "categoria": "precedente_interno",
  "tribunal": "TJMG",
  "versao": 2,
  "vigente": true,
  "revisado": true,
  "hash_conteudo": "sha1",
  "status_fonte": "confirmada",
  "motivos_status": ["documento aprovado, revisado ou conferido"]
}
```

`client_id` não é exposto no contrato. O isolamento continua sendo executado
na consulta SQL e na camada de autorização; a proveniência não pode ser usada
para ampliar o escopo de dados do usuário.

## Metadados opcionais no JSONB

Quando disponíveis, devem ser gravados em `extra["proveniencia"]`:

```json
{
  "proveniencia": {
    "nome_arquivo": "acordao.pdf",
    "pagina": 8,
    "data_documento": "2026-06-20",
    "processo_origem": "0000000-00.2026.8.13.0000",
    "url": "https://fonte-oficial.example/documento",
    "status_fonte": "confirmada",
    "vigencia_status": "vigente",
    "fonte_localizada": true
  }
}
```

Não se deve inferir página a partir do `chunk_index`. A página somente pode ser
exibida quando a extração/OCR preservar a relação real entre página e trecho.

## Aplicação nos fluxos

### Leitor de autos

Cada fato, pedido, decisão, prazo aparente e prova deve apontar para uma ou mais
proveniências. Prazos extraídos permanecem como **aparentes** até confirmação
humana.

### Modo Molde

O sistema deve registrar o documento e a versão usados como molde. Antes de
liberar a nova peça, deve procurar resíduos do caso anterior e marcar fontes
não localizadas ou desatualizadas.

### Modo Agente

A etapa de planejamento deve apresentar documentos considerados, fatos
identificados, lacunas e estados das fontes antes da redação. A redação só pode
começar após aprovação humana.

### Resposta da IA

A interface deve diferenciar claramente:

- documento do caso;
- precedente interno;
- fonte oficial;
- doutrina autorizada;
- inferência da IA.

Uma fonte `nao_localizada`, `identificacao_insuficiente` ou
`possivelmente_desatualizada` deve gerar alerta e nunca ser apresentada como
fundamento jurídico confirmado.

## Evolução sem migration

A primeira fase usa JSONB para validar o contrato com dados reais. Uma migration
futura só será proposta se houver necessidade comprovada de índice, filtro ou
relatório sobre campos específicos. Qualquer promoção para colunas deverá ter
upgrade, downgrade, teste com banco real e rollback documentado.
