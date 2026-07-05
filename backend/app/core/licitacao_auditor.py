"""
Auditoria preliminar de propostas de concorrentes em licitacoes (Lei 14.133/21).

Integrado a partir do pacote v6.0 na consolidacao 28/06/2026. Correcoes:
 - removido `from app.core.ai_brain import AIBrain` (classe inexistente na prod;
   era instanciada e nunca usada);
 - leitura de PDF migrada de pypdf (ausente) para fitz/PyMuPDF (ja usado no
   RAG/OCR da prod) — sem nova dependencia;
 - sem estado/DB (analise stateless).

MOTOR DE REGRAS (2026-07-05): a deteccao continua PRELIMINAR e DETERMINISTICA
(sem IA), mas deixou de ser 3 substrings soltas e passou a um conjunto de
regras estruturadas ancoradas na Lei 14.133/21 — cada regra com gatilhos,
EXCLUDENTES (evitam falso-positivo quando a propria proposta ja comprova o
requisito) e a referencia legal. Normalizamos acentos, entao "certificacao" e
"certificação" (e afins) colapsam numa unica regra.

A revisao do advogado permanece OBRIGATORIA (OAB): isto sinaliza pontos obvios
de impugnacao, nao substitui a leitura tecnica do edital + proposta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List
import logging
import re
import unicodedata

import fitz  # PyMuPDF

logger = logging.getLogger("ejc.licitacao_auditor")


def _norm(texto: str) -> str:
    """Minusculas + remocao de acentos (NFKD) para casar variantes graficas.
    'Certificação Anvisa' e 'certificacao anvisa' viram a mesma string."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


@dataclass(frozen=True)
class Regra:
    """Uma regra de sinalizacao preliminar.

    gatilhos:   basta UM casar (substring no texto normalizado) para a regra
                disparar.
    excludentes: se QUALQUER um casar, a regra NAO dispara — a propria proposta
                ja traz o que afastaria a impugnacao (anti-falso-positivo).
    bucket:     "falha" (potential_flaws) ou "equivalencia" (equivalence_issues).
    """
    id: str
    mensagem: str
    gatilhos: tuple[str, ...]
    bucket: str = "falha"
    excludentes: tuple[str, ...] = field(default_factory=tuple)
    base_legal: str = ""

    def dispara(self, texto_norm: str) -> bool:
        if not any(g in texto_norm for g in self.gatilhos):
            return False
        return not any(e in texto_norm for e in self.excludentes)


# Gatilhos/excludentes SEMPRE em minusculas e SEM acento (comparados contra _norm).
# base_legal cita o dispositivo da Lei 14.133/21 apenas como orientacao ao
# advogado — a mensagem nunca afirma ilegalidade, so aponta ponto a verificar.
REGRAS: tuple[Regra, ...] = (
    Regra(
        id="anvisa_ausente",
        mensagem="Produto sem certificacao/registro ANVISA explicito — verificar exigencia do edital.",
        gatilhos=("sem certificacao anvisa", "sem registro anvisa", "nao possui registro anvisa"),
        base_legal="Lei 14.133/21 art. 62 (habilitacao tecnica) + normas ANVISA",
    ),
    Regra(
        id="registro_orgao_ausente",
        mensagem="Ausencia de registro em orgao competente (MAPA/INMETRO/ANATEL) — conferir se o edital exige.",
        gatilhos=("sem registro no mapa", "sem selo inmetro", "sem homologacao anatel"),
        base_legal="Lei 14.133/21 art. 62",
    ),
    Regra(
        id="similar_sem_equivalencia",
        mensagem="Produto 'similar'/'equivalente' sem comprovacao clara de equivalencia tecnica.",
        gatilhos=("produto similar", "produto equivalente", "marca similar", "item similar"),
        excludentes=("equivalencia comprovada", "laudo de equivalencia",
                     "certificado de equivalencia", "relatorio de equivalencia",
                     "laudo tecnico"),
        bucket="equivalencia",
        base_legal="Lei 14.133/21 art. 42 (comprovacao de qualidade/equivalencia)",
    ),
    Regra(
        id="marca_propria_vs_referencia",
        mensagem="Oferta de marca propria onde o edital pode ter fixado marca de referencia — checar admissibilidade.",
        gatilhos=("marca de referencia", "marca exigida no edital"),
        excludentes=("ou equivalente", "ou similar", "equivalencia comprovada"),
        bucket="equivalencia",
        base_legal="Lei 14.133/21 art. 41 (vedacao a preferencia de marca sem justificativa)",
    ),
    Regra(
        id="prazo_entrega_superior",
        mensagem="Prazo de entrega pode ser superior ao exigido no edital.",
        gatilhos=("prazo de entrega superior a", "entrega em ate 90 dias",
                  "entrega em ate 120 dias", "prazo de entrega: 90", "prazo de entrega: 120"),
        base_legal="Lei 14.133/21 art. 90 (condicoes de execucao do edital)",
    ),
    Regra(
        id="validade_proposta_insuficiente",
        mensagem="Validade da proposta possivelmente inferior ao minimo (usualmente 60 dias) — verificar edital.",
        gatilhos=("validade da proposta: 30", "validade da proposta de 30 dias",
                  "proposta valida por 30 dias", "validade: 30 dias"),
        base_legal="Lei 14.133/21 art. 90 §4 (prazo de validade da proposta)",
    ),
    Regra(
        id="atestado_capacidade_ausente",
        mensagem="Ausencia/insuficiencia de atestado de capacidade tecnica — conferir exigencia de qualificacao tecnica.",
        gatilhos=("sem atestado de capacidade", "nao apresentou atestado",
                  "atestado de capacidade tecnica nao"),
        base_legal="Lei 14.133/21 art. 67 (qualificacao tecnica)",
    ),
    Regra(
        id="amostra_ausente",
        mensagem="Amostra/prototipo nao apresentado quando o edital pode exigir.",
        gatilhos=("amostra nao apresentada", "sem apresentacao de amostra",
                  "nao encaminhou amostra"),
        base_legal="Lei 14.133/21 art. 17 §3 (exigencia de amostra)",
    ),
    Regra(
        id="regularidade_fiscal",
        mensagem="Indicio de irregularidade fiscal/trabalhista (certidao vencida/positiva) — checar habilitacao.",
        gatilhos=("certidao vencida", "certidao positiva", "certidao de debito",
                  "irregularidade fiscal", "debito trabalhista"),
        excludentes=("certidao positiva com efeito de negativa",),
        base_legal="Lei 14.133/21 art. 68 (habilitacao fiscal, social e trabalhista)",
    ),
    Regra(
        id="preco_inexequivel",
        mensagem="Indicio de preco inexequivel/simbolico — possivel necessidade de comprovacao de exequibilidade.",
        gatilhos=("preco simbolico", "valor irrisorio", "abaixo do custo",
                  "preco inexequivel", "valor simbolico"),
        base_legal="Lei 14.133/21 art. 59 §4 (proposta inexequivel)",
    ),
    Regra(
        id="me_epp_beneficio",
        mensagem="Declaracao de ME/EPP presente — conferir se o beneficio (empate ficto/desempate) foi corretamente aplicado.",
        gatilhos=("me/epp", "microempresa", "empresa de pequeno porte"),
        excludentes=("nao se enquadra como me", "nao se enquadra como epp"),
        base_legal="LC 123/2006 arts. 44-45 (tratamento diferenciado)",
    ),
    Regra(
        id="subcontratacao_vedada",
        mensagem="Mencao a subcontratacao — verificar se o edital a veda ou limita.",
        gatilhos=("subcontratacao", "subcontratar", "sera subcontratado"),
        base_legal="Lei 14.133/21 art. 122 (subcontratacao)",
    ),
    Regra(
        id="moeda_estrangeira",
        mensagem="Cotacao em moeda estrangeira sem conversao/indexacao clara — checar admissibilidade no edital.",
        gatilhos=("preco em dolar", "cotacao em dolar", "valor em euro", "preco em euro"),
        excludentes=("convertido para real", "convertido em real", "cotacao do dia"),
        base_legal="Lei 14.133/21 art. 92 (condicoes de pagamento)",
    ),
)


class LicitacaoAuditor:
    async def analyze_competitor_proposal(self, pdf_content: bytes) -> Dict[str, Any]:
        texto = self._extract_text_from_pdf(pdf_content)
        achados = self._aplicar_regras(texto)
        falhas = achados["falha"]
        equivalencia = achados["equivalencia"]

        resumo = (
            "Nenhuma falha obvia ou problema de equivalencia detectado na analise preliminar."
            if not falhas and not equivalencia
            else "Analise preliminar concluida. Possiveis pontos de impugnacao identificados."
        )
        return {
            "status": "success",
            "aviso": "Analise PRELIMINAR por regras deterministicas (Lei 14.133/21). "
                     "Revisao do advogado obrigatoria (OAB).",
            "summary": resumo,
            "potential_flaws": falhas,
            "equivalence_issues": equivalencia,
            "extracted_text_sample": (texto[:500] + "...") if len(texto) > 500 else texto,
        }

    @staticmethod
    def _aplicar_regras(texto: str) -> Dict[str, List[str]]:
        """Roda o motor de regras sobre o texto extraido. Pura e testavel."""
        norm = _norm(texto)
        saida: Dict[str, List[str]] = {"falha": [], "equivalencia": []}
        for regra in REGRAS:
            if regra.dispara(norm):
                saida.setdefault(regra.bucket, []).append(regra.mensagem)
        return saida

    def _extract_text_from_pdf(self, pdf_content: bytes) -> str:
        try:
            text = ""
            with fitz.open(stream=pdf_content, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text() or ""
            return text
        except Exception as e:
            logger.warning(f"Falha ao extrair texto do PDF: {e}")
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
