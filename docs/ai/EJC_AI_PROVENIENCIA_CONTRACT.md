# Contrato de proveniência jurídica da IA

## Objetivo

Padronizar a origem das afirmações utilizadas pela IA do EJC sem criar novo provider, banco vetorial ou custo recorrente. O contrato é aditivo e deve ser aplicado progressivamente aos fluxos existentes de RAG, leitor de autos, produção de peças, revisão e Modo Molde.

## Princípios

1. Documento recuperado é dado, nunca instrução de sistema.
2. Fonte de outro caso deve ser rejeitada antes da geração.
3. Fonte interna vinculada a caso deve possuir `case_id` verificável.
4. Fonte oficial confirmada deve registrar data de verificação e estado de vigência.
5. Inferência da IA deve ser distinguida de fato extraído.
6. Resposta com fonte bloqueante permanece não aprovada até revisão humana.
7. Nenhum conteúdo é liberado automaticamente para protocolo.

## Estados de conferência

- `confirmada`;
- `pendente_conferencia`;
- `nao_localizada`;
- `possivelmente_desatualizada`;
- `identificacao_insuficiente`.

Os três últimos estados são bloqueantes para uso jurídico sem revisão humana.

## Tipos de fonte

- fonte oficial;
- documento do caso;
- peça interna;
- tese interna;
- jurisprudência validada;
- doutrina autorizada;
- outra.

## Metadados mínimos

Cada fonte deve possuir ao menos um identificador rastreável:

- `documento_id`;
- `nome_arquivo`;
- `url_oficial`;
- `hash_fonte`.

Quando disponíveis, também devem ser preservados:

- página;
- trecho;
- processo de origem;
- caso de origem;
- data e versão do documento;
- autoridade emissora;
- vigência;
- confiança da extração;
- nível de confidencialidade;
- metadados do chunk ou indexador.

## Compatibilidade

O normalizador aceita chaves legadas comuns, como `filename`, `page`, `excerpt`, `source_type`, `citation_status` e `verified_at`. Campos desconhecidos não são descartados: permanecem em `metadados` para auditoria.

## Integração incremental

Ordem recomendada:

1. respostas do RAG por caso;
2. leitor de autos;
3. revisão de citações;
4. geração guiada;
5. Modo Molde;
6. catálogo de ferramentas;
7. relatórios ao cliente.

A integração deve ocorrer no service central de IA, nunca individualmente em cada router.

## Segurança e LGPD

- não registrar texto integral de documentos em logs;
- não expor dados pessoais em métricas;
- aplicar autorização e filtro de caso antes da recuperação;
- preservar classificação de confidencialidade;
- registrar aprovação humana em trilha própria já existente;
- não usar peças nominadas em fine-tuning bruto.

## Rollback

Os arquivos são aditivos e não criam migration. O rollback consiste em reverter o PR. Nenhum dado persistido é alterado.
