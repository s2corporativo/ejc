# ── app/services/calc/prescricao.py ──────────────────────────────────────────
# Motor de prescrição e decadência — tabela curada de prazos com BASE LEGAL
# expressa. Calcula a data-limite a partir do termo inicial (fato/violação/
# ciência), respeitando as regras de contagem de cada ramo.
#
# ⚠️ Conhecimento jurídico estável (artigos de código). Ainda assim, o resultado
# é uma MINUTA de orientação (HITL): suspensões, interrupções e causas
# específicas do caso concreto devem ser avaliadas pelo advogado.
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from dateutil.relativedelta import relativedelta   # python-dateutil (já no stack)

# Catálogo de prazos. Cada item: chave, rótulo, anos OU dias, tipo, base legal,
# termo inicial típico e observações. Curado a partir de CC, CLT, CTN, CDC.
PRAZOS: dict[str, dict] = {
    # ── Cível (Código Civil) ─────────────────────────────────────────────────
    "civel_geral": {
        "rotulo": "Prescrição geral (pretensões pessoais)", "anos": 10,
        "tipo": "prescricao", "base_legal": "CC, art. 205",
        "termo_inicial": "violação do direito (actio nata)",
        "obs": "Aplica-se quando a lei não fixar prazo menor.",
    },
    "reparacao_civil": {
        "rotulo": "Reparação civil (responsabilidade extracontratual)", "anos": 3,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §3º, V",
        "termo_inicial": "data do dano/ciência da autoria",
    },
    "cobranca_liquida": {
        "rotulo": "Cobrança de dívida líquida (instrumento público/particular)", "anos": 5,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §5º, I",
        "termo_inicial": "vencimento da dívida",
    },
    "honorarios_profissionais": {
        "rotulo": "Honorários de profissionais liberais", "anos": 5,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §5º, II",
        "termo_inicial": "conclusão dos serviços ou cessação do contrato",
    },
    "enriquecimento_sem_causa": {
        "rotulo": "Ressarcimento de enriquecimento sem causa", "anos": 3,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §3º, IV",
        "termo_inicial": "data do pagamento indevido",
    },
    "seguro": {
        "rotulo": "Pretensão do segurado contra segurador", "anos": 1,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §1º, II",
        "termo_inicial": "ciência do fato gerador",
    },
    "alugueis": {
        "rotulo": "Cobrança de aluguéis", "anos": 3,
        "tipo": "prescricao", "base_legal": "CC, art. 206, §3º, I",
        "termo_inicial": "vencimento de cada aluguel",
    },
    # ── Consumidor (CDC) ──────────────────────────────────────────────────────
    "cdc_reparacao_fato": {
        "rotulo": "Reparação por fato do produto/serviço (acidente de consumo)", "anos": 5,
        "tipo": "prescricao", "base_legal": "CDC, art. 27",
        "termo_inicial": "conhecimento do dano e da autoria",
    },
    "cdc_vicio_nao_duravel": {
        "rotulo": "Reclamação por vício — produto/serviço NÃO durável", "dias": 30,
        "tipo": "decadencia", "base_legal": "CDC, art. 26, I",
        "termo_inicial": "entrega efetiva / término do serviço (vício aparente)",
    },
    "cdc_vicio_duravel": {
        "rotulo": "Reclamação por vício — produto/serviço durável", "dias": 90,
        "tipo": "decadencia", "base_legal": "CDC, art. 26, II",
        "termo_inicial": "entrega efetiva / término do serviço (vício aparente)",
    },
    # ── Trabalhista (CLT / CF) ────────────────────────────────────────────────
    "trabalhista_quinquenal": {
        "rotulo": "Créditos trabalhistas — prescrição quinquenal", "anos": 5,
        "tipo": "prescricao", "base_legal": "CF, art. 7º, XXIX; CLT, art. 11",
        "termo_inicial": "exigibilidade da parcela (na vigência do contrato)",
        "obs": "Limitada aos 5 anos anteriores ao ajuizamento.",
    },
    "trabalhista_bienal": {
        "rotulo": "Créditos trabalhistas — prescrição bienal (após extinção)", "anos": 2,
        "tipo": "prescricao", "base_legal": "CF, art. 7º, XXIX; CLT, art. 11",
        "termo_inicial": "extinção do contrato de trabalho",
        "obs": "Prazo fatal para ajuizar após o fim do contrato.",
    },
    # ── Tributário (CTN) ──────────────────────────────────────────────────────
    "tributario_decadencia": {
        "rotulo": "Decadência do lançamento tributário", "anos": 5,
        "tipo": "decadencia", "base_legal": "CTN, art. 173, I",
        "termo_inicial": "1º dia do exercício seguinte ao que poderia lançar",
        "obs": "Para tributos por homologação, ver CTN art. 150, §4º.",
    },
    "tributario_prescricao": {
        "rotulo": "Prescrição da cobrança do crédito tributário", "anos": 5,
        "tipo": "prescricao", "base_legal": "CTN, art. 174",
        "termo_inicial": "constituição definitiva do crédito",
    },
}


@dataclass
class EntradaPrescricao:
    chave: str
    termo_inicial: date


def calcular(e: EntradaPrescricao, hoje: date | None = None) -> dict:
    """Calcula a data-limite e a situação (em curso / consumada). MINUTA — HITL."""
    if e.chave not in PRAZOS:
        raise ValueError(f"Prazo desconhecido. Use: {list(PRAZOS)}")
    p = PRAZOS[e.chave]
    hoje = hoje or date.today()

    if "anos" in p:
        limite = e.termo_inicial + relativedelta(years=p["anos"])
        prazo_desc = f"{p['anos']} ano(s)"
    else:
        limite = e.termo_inicial + relativedelta(days=p["dias"])
        prazo_desc = f"{p['dias']} dia(s)"

    dias_restantes = (limite - hoje).days
    consumada = dias_restantes < 0

    return {
        "prazo": p["rotulo"],
        "tipo": p["tipo"],                 # prescricao | decadencia
        "base_legal": p["base_legal"],
        "termo_inicial": e.termo_inicial.isoformat(),
        "termo_inicial_descricao": p["termo_inicial"],
        "duracao": prazo_desc,
        "data_limite": limite.isoformat(),
        "dias_restantes": dias_restantes,
        "situacao": "consumada" if consumada else "em_curso",
        "alerta": (
            "PRAZO PROVAVELMENTE CONSUMADO — confirmar causas de suspensão/interrupção."
            if consumada else
            ("ATENÇÃO: prazo se encerra em breve." if dias_restantes <= 180 else "")
        ),
        "observacao": p.get("obs", ""),
        "avisos": [
            "MINUTA de orientação (HITL) — sujeita à revisão do advogado.",
            "Não considera automaticamente suspensões/interrupções (CC arts. 197-204), "
            "feriados, nem particularidades do caso concreto.",
        ],
    }
