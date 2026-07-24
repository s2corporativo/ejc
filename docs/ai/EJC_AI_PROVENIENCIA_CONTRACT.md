# Contrato de proveniência jurídica da IA

## Objetivo

Padronizar a origem das afirmações utilizadas pela IA do EJC sem criar novo
provider, banco vetorial ou custo recorrente. O contrato é aditivo e deve ser
aplicado progressivamente aos fluxos existentes de RAG, leitor de autos,
produção de peças, revisão e Modo Molde.

## Princípios

1. Documento recuperado é dado, nunca instrução de sistema.
2. Fonte de outro caso deve ser rejeitada antes da geração.
3. Fonte interna vinculada a caso deve possuir `case_id` verificável.
4. Fonte oficial confirmada deve registrar data de verificação e estado de vigência.
5. Inferência da IA deve ser distinguida de fato extraído.
6. Resposta com fonte bloqueante permanece não aprovada até revisão humana.
7. Nenhum conteúdo é liberado automaticamente para protocolo.
8. Fonte sem classificação explícita nasce como `interna`, nunca como pública.
9. Fonte em segredo de justiça exige `case_id` verificável.
10. Registros conflitantes de status ou confidencialidade não são deduplicados.
11. Metadados de proveniência não transportam identificadores pessoais ou segredos.
12. Aprovação humana só é válida com responsável, data e registro de auditoria.

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

## Níveis de confidencialidade

- `publica`;
- `interna`;
- `confidencial`;
- `restrita`;
- `segredo_justica`.

O padrão é `interna`. A classificação pública deve ser explícita. O nível de
confidencialidade é metadado de governança e não substitui RBAC, filtro de caso,
restrições documentais ou segregação por cliente.

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
- metadados técnicos do chunk ou indexador.

## Minimização LGPD

O campo `metadados` é sanitizado recursivamente. Chaves conhecidas de dados
pessoais, escopo interno e credenciais são removidas, inclusive em listas e
objetos aninhados. Exemplos:

- `client_id`, `tenant_id`, `user_id` e `owner_id`;
- CPF, CNPJ, RG, telefone, e-mail e endereço;
- token, secret, senha, password, API key, authorization e cookie.

O normalizador preserva apenas metadados técnicos necessários à auditoria, como
`chunk_id`, índice, categoria, tribunal e motivos da classificação. O texto
integral do documento não deve ser copiado para `metadados`.

## Compatibilidade

O normalizador aceita chaves legadas comuns, como:

- `filename`;
- `page`;
- `excerpt`;
- `source_type`;
- `citation_status`;
- `confidentiality`;
- `confidentiality_level`;
- `privacy_level`;
- `verified_at`.

Campos desconhecidos não sensíveis permanecem em `metadados` para auditoria.
Campos pessoais ou secretos são descartados pelo contrato.

## Deduplicação

A deduplicação só remove fontes semanticamente idênticas. Status de conferência,
confidencialidade e marca de inferência integram a chave. Assim, uma versão
`restrita` ou `nao_localizada` nunca é ocultada por outra mais permissiva da
mesma página ou trecho.

## Aprovação humana auditável

`aprovado_humano` nasce como `false`. Para assumir `true`, o envelope deve
informar simultaneamente:

- `aprovado_por`;
- `aprovado_em`;
- `registro_aprovacao_id` vinculado à auditoria do EJC;
- zero fontes bloqueantes no resumo de confiabilidade.

A ausência de qualquer evidência invalida o envelope. A aprovação do plano ou da
estrutura não equivale à aprovação da peça final.

## Integração incremental

Ordem recomendada:

1. respostas do RAG por caso;
2. leitor de autos;
3. revisão de citações;
4. geração guiada;
5. Modo Molde;
6. catálogo de ferramentas;
7. relatórios ao cliente.

A integração deve ocorrer no service central de IA, nunca individualmente em
cada router.

## Segurança e LGPD

- não registrar texto integral de documentos em logs;
- não expor dados pessoais em métricas ou proveniência;
- aplicar autorização e filtro de caso antes da recuperação;
- preservar classificação de confidencialidade;
- registrar aprovação humana em trilha própria já existente;
- não usar peças nominadas em fine-tuning bruto;
- não rebaixar sigilo por deduplicação ou fallback;
- não tratar confidencialidade como autorização de acesso;
- não aceitar aprovação sem evidência de auditoria.

## Rollback

Os arquivos são aditivos e não criam migration. O rollback consiste em reverter
o PR. Nenhum dado persistido é alterado.
