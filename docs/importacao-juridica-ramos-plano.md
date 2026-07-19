# Plano técnico — importação jurídica por ramos

## Objetivo

Evoluir o pipeline atual de importação inteligente do EJC para classificar documentos por ramo do Direito, extrair dados estruturados e gerar análise especializada com revisão humana obrigatória.

## Arquitetura recomendada

Criar um pacote em `backend/app/services/document_intelligence/` com:

- `domain_classifier.py`: identifica tipo documental e ramo jurídico principal/secundário.
- `orchestrator.py`: coordena classificação, análise especializada e integração com o pipeline existente.
- `schemas.py`: define JSON universal de resposta.
- `evidence.py`: registra trechos de origem e grau de confiança.
- `validators.py`: aplica travas contra inferência indevida.
- `analyzers/`: analisadores por ramo.

## Integração obrigatória

Reaproveitar:

- `backend/app/routers/documento_ia.py`;
- `backend/app/services/documento_service.py`;
- OCR existente;
- sanitização de dados sensíveis;
- núcleo único de IA;
- RAG;
- auditoria;
- revisão humana obrigatória.

A rota atual `/api/documentos-ia/analisar` não pode ser quebrada.

## Ramos mínimos

- Empresarial
- Cível
- Penal
- Trabalhista
- Administrativo
- Bancário
- Tributário
- Ambiental
- Saúde
- Imobiliário
- Consumidor
- Internacional
- Previdenciário
- Família
- Digital/LGPD
- Trânsito

## Prioridade de implementação

1. Motor comum de classificação e JSON universal.
2. Analisador bancário para contratos, CCB, empréstimos e extratos.
3. Analisador tributário para XML, notas, autos fiscais e CDA.
4. Analisador de trânsito para multas, CNH e recursos administrativos.
5. Analisador trabalhista para CTPS, TRCT, holerites, ponto, FGTS e verbas.
6. Analisadores complementares para os demais ramos.
7. Tela de relatório no frontend.
8. Testes automatizados e relatório final.

## JSON universal mínimo

```json
{
  "classificacao": {},
  "partes": [],
  "datas_relevantes": [],
  "valores_relevantes": [],
  "prazos": [],
  "obrigacoes": [],
  "penalidades": [],
  "clausulas_relevantes": [],
  "riscos": [],
  "pontos_fortes": [],
  "pontos_criticos": [],
  "brechas_juridicas": [],
  "teses_possiveis": [],
  "providencias_recomendadas": [],
  "documentos_complementares": [],
  "calculos_recomendados": [],
  "pecas_possiveis": [],
  "analise_juridica": null,
  "nivel_urgencia": null,
  "necessita_revisao_humana": true
}
```

## Critérios de aceite

- Classificar o documento por ramo.
- Extrair dados detalhados.
- Separar dado extraído, inferência e recomendação.
- Preservar revisão humana obrigatória.
- Não inventar fatos, prazos, valores, leis ou jurisprudência.
- Gerar relatório visual.
- Criar ações no sistema: caso, cliente, prazo, tarefa, alerta, checklist e minuta.
- Ter testes com documentos fictícios por ramo prioritário.
