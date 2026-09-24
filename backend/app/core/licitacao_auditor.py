"""
Auditoria preliminar de propostas de concorrentes em licitacoes (Lei 14.133/21).

Integrado a partir do pacote v6.0 na consolidacao 28/06/2026. Correcoes:
 - removido `from app.core.ai_brain import AIBrain` (classe inexistente na prod;
   era instanciada e nunca usada);
 - leitura de PDF migrada de pypdf (ausente) para fitz/PyMuPDF (ja usado no
   RAG/OCR da prod) — sem nova dependencia;
 - sem estado/DB (analise stateless).

IMPORTANTE: a deteccao e PRELIMINAR e DETERMINISTICA (palavras-chave), nao IA.
Serve para sinalizar pontos obvios de impugnacao; a revisao do advogado e
obrigatoria (OAB).
"""
from typing import Dict, Any
import logging

import fitz  # PyMuPDF

logger = logging.getLogger("ejc.licitacao_auditor")


class LicitacaoAuditor:
    async def analyze_competitor_proposal(self, pdf_content: bytes) -> Dict[str, Any]:
        texto = self._extract_text_from_pdf(pdf_content)
        low = texto.lower()
        falhas = []
        equivalencia = []

        if "sem certificacao anvisa" in low or "sem certificação anvisa" in low:
            falhas.append("Produto sem certificacao ANVISA explicita.")
        if ("produto similar" in low
                and "equivalencia comprovada" not in low
                and "equivalência comprovada" not in low):
            equivalencia.append("Produto similar sem comprovacao clara de equivalencia tecnica.")
        if "prazo de entrega superior a" in low:
            falhas.append("Prazo de entrega pode ser superior ao exigido no edital.")

        resumo = (
            "Nenhuma falha obvia ou problema de equivalencia detectado na analise preliminar."
            if not falhas and not equivalencia
            else "Analise preliminar concluida. Possiveis pontos de impugnacao identificados."
        )
        return {
            "status": "success",
            "aviso": "Analise PRELIMINAR por palavras-chave. Revisao do advogado obrigatoria (OAB).",
            "summary": resumo,
            "potential_flaws": falhas,
            "equivalence_issues": equivalencia,
            "extracted_text_sample": (texto[:500] + "...") if len(texto) > 500 else texto,
        }

    def _extract_text_from_pdf(self, pdf_content: bytes) -> str:
        try:
            text = ""
            with fitz.open(stream=pdf_content, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text() or ""
            return text
        except Exception as e:
            # Não registrar mensagem bruta da exceção: PDFs podem carregar
            # nomes/caminhos/metadados sensíveis em erros de parser.
            logger.warning("Falha ao extrair texto do PDF (%s)", type(e).__name__)
            return ""

    async def get_audit_report_template(self) -> str:
        return """# Relatorio de Auditoria de Proposta de Concorrente

## Analise de Edital: [Nome do Edital]
### Concorrente: [Nome do Concorrente]
### Data da Analise: [Data]

## Sumario Executivo
[Resumo da analise, destacando pontos fortes e fracos da proposta do concorrente
em relacao ao edital.]

## Pontos de Impugnacao Potenciais
*   **[Ponto 1]:** [Descricao da falha, com referencia a clausula do edital e
    evidencia na proposta.]

## Questoes de Equivalencia Tecnica
*   **[Produto/Servico 1]:** [Descricao do problema de equivalencia, com
    comparacao aos requisitos do edital.]

## Recomendacoes
*   [Acao recomendada 1]

## Evidencias (Trechos da Proposta)
```text
[Trecho relevante da proposta do concorrente]
```

---
*Gerado pelo EJC — analise preliminar; revisao humana obrigatoria.*
"""
