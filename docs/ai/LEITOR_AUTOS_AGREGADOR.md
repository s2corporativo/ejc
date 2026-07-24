# Leitor de autos — agregador determinístico

## Finalidade

Consolidar múltiplos resultados de `DocumentoIntakeResult` em uma visão única dos
autos, sem nova chamada de IA e sem substituir o pipeline documental existente.

## Pipeline reutilizado

```text
arquivo
  -> ocr_service
  -> extracao_estruturada local
  -> documento_service.extrair_e_analisar
  -> DocumentoIntakeResult
  -> leitor_autos_service.agregar_autos
```

O agregador não abre banco, não acessa arquivo, não executa OCR e não chama LLM.

## Saída atual

- índice dos documentos;
- partes e papéis identificados;
- resumos fáticos por documento;
- pedidos;
- provas;
- prazos com termo final explícito;
- cronologia formada apenas por datas parseáveis;
- riscos;
- teses sugeridas;
- lacunas e pendências;
- avisos de fonte não confirmada ou análise parcial;
- estatísticas do conjunto.

Cada informação consolidada mantém referência ao documento, arquivo, página,
status da fonte, trecho de origem e confiança quando esses dados existem.

## Regras fail-safe

1. Entrada ausente gera resultado vazio, nunca conteúdo inventado.
2. Prazo sem termo final explícito não entra no quadro de prazos.
3. Data não parseável não entra na cronologia.
4. Fonte diferente de `confirmada` gera aviso.
5. Análise parcial gera lacuna de severidade alta.
6. Todo resultado permanece com `necessita_revisao_humana=true`.
7. O agregador não materializa `Deadline`, não cria caso e não gera peça.

## Lacunas ainda não suportadas pelo contrato atual

O `DocumentoIntakeResult` atual não possui campos específicos e rastreáveis para:

- decisões judiciais;
- fatos controvertidos;
- relação fato-prova estruturada;
- classificação individual de cada documento dos autos por página;
- pedidos separados quando o intake devolve todos em um único texto.

Esses dados não são inferidos pelo agregador. A evolução correta é ampliar o
contrato do intake com trecho de origem e confiança, testar a extração e somente
depois incorporá-los ao leitor.

## Integração futura

1. receber os documentos já analisados e autorizados de um caso;
2. validar acesso ao caso no router;
3. construir `DocumentoAutosEntrada` com a proveniência do RAG/GED;
4. chamar `agregar_autos`;
5. devolver o dossiê como minuta;
6. persistir snapshot apenas após definição de versionamento e auditoria;
7. nunca criar prazo ou peça sem confirmação humana nos endpoints próprios.

## Rollback

A remoção do schema, serviço, testes e deste documento restaura o estado anterior.
Não há migration nem dado persistido.
