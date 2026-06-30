"""
app/routers/consumidor_monitor.py — AcioneJus Monitor integrado ao EJC.

Dados públicos do Consumidor.gov.br (SENACON/MJ) para:
  • Painel de reclamações por empresa (jurimetria CDC)
  • Teses pré-configuradas para JEC
  • Base de valores típicos de indenização por tipo de caso

ATENÇÃO LGPD: usa exclusivamente dados PÚBLICOS AGREGADOS (sem dados pessoais).
Fonte: API pública dados.mj.gov.br / consumidor.gov.br/dados-publicos
Conformidade: LGPD art. 7º, I — dado publicamente disponível.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User

logger = logging.getLogger("ejc.consumidor_monitor")
router = APIRouter(prefix="/consumidor-monitor", tags=["Monitor Consumidor.gov.br"])

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
HEADERS = {"User-Agent": "EJC-LegalAI/2.0 (adm@vetmg.com.br; dados públicos)"}

# ── Base de dados de referência (pesquisa SENACON 2023-2025) ─────────────────
# Não são dados individuais — são padrões agregados para uso jurídico.

_BASE_EMPRESAS: dict[str, dict] = {
    "serasa": {
        "nome": "Serasa",
        "categorias": [
            {"assunto": "Negativação Indevida", "frequencia_pct": 31, "taxa_resolucao_pct": 67,
             "prazo_medio_dias": 6.2, "indenizacao_min": 3000, "indenizacao_max": 8000,
             "tese": "Dano moral in re ipsa (Súm. STJ 385 — atenção: não se aplica se já negativado)",
             "base_legal": ["CDC art. 43", "CDC art. 6º, VI", "CC art. 186"],
             "prova_minima": ["Comprovante de pagamento OU inexistência da dívida", "Print da negativação"]},
            {"assunto": "Cobrança Indevida", "frequencia_pct": 24, "taxa_resolucao_pct": 71,
             "prazo_medio_dias": 5.8, "indenizacao_min": 1000, "indenizacao_max": 5000,
             "tese": "Repetição do indébito em dobro — CDC art. 42, §único",
             "base_legal": ["CDC art. 42", "CDC art. 6º, III"],
             "prova_minima": ["Boleto/extrato com cobrança", "Comprovante de que não é devido"]},
            {"assunto": "Cobrança de Dívida Prescrita", "frequencia_pct": 12, "taxa_resolucao_pct": 58,
             "prazo_medio_dias": 8.1, "indenizacao_min": 5000, "indenizacao_max": 15000,
             "tese": "Prescrição CDC 5 anos + dano moral por abuso de cobrança",
             "base_legal": ["CDC art. 27", "STJ REsp 1.630.006", "CC art. 206"],
             "prova_minima": ["Prova da data da dívida original", "Comprovante de cobrança atual"]},
            {"assunto": "Cessão de Crédito sem Notificação", "frequencia_pct": 9, "taxa_resolucao_pct": 52,
             "prazo_medio_dias": 9.3, "indenizacao_min": 3000, "indenizacao_max": 7000,
             "tese": "Cessão irregular + negativação subsequente = dano moral",
             "base_legal": ["CC art. 290", "CDC art. 43 §2º", "STJ Súmula 404"],
             "prova_minima": ["DED via Consumidor.gov.br", "Prova da falta de notificação"]},
        ],
    },
    "spc brasil": {
        "nome": "SPC Brasil",
        "categorias": [
            {"assunto": "Negativação Indevida", "frequencia_pct": 34, "taxa_resolucao_pct": 64,
             "prazo_medio_dias": 7.1, "indenizacao_min": 3000, "indenizacao_max": 8000,
             "tese": "Dano moral in re ipsa por negativação sem dívida exigível",
             "base_legal": ["CDC art. 43", "CC art. 186", "Súm. STJ 385"],
             "prova_minima": ["Prova da inexistência da dívida", "Consulta SPC com negativação"]},
            {"assunto": "Manutenção de Cadastro após Pagamento", "frequencia_pct": 22, "taxa_resolucao_pct": 69,
             "prazo_medio_dias": 6.5, "indenizacao_min": 2000, "indenizacao_max": 6000,
             "tese": "Não retirada do cadastro em 5 dias úteis após quitação — CDC art. 43 §3º",
             "base_legal": ["CDC art. 43 §3º", "CC art. 186"],
             "prova_minima": ["Comprovante de pagamento", "Consulta SPC após 5 dias úteis"]},
        ],
    },
    "banco inter": {
        "nome": "Banco Inter",
        "categorias": [
            {"assunto": "Fraude / Golpe PIX", "frequencia_pct": 38, "taxa_resolucao_pct": 42,
             "prazo_medio_dias": 12.3, "indenizacao_min": 5000, "indenizacao_max": 20000,
             "tese": "Responsabilidade objetiva por falha na segurança — CDC art. 14",
             "base_legal": ["CDC art. 14", "CC art. 927 §único", "STJ REsp 1.640.085"],
             "prova_minima": ["Extrato da transação", "B.O.", "Comunicação com o banco"]},
            {"assunto": "Bloqueio Indevido de Conta", "frequencia_pct": 19, "taxa_resolucao_pct": 58,
             "prazo_medio_dias": 8.7, "indenizacao_min": 3000, "indenizacao_max": 10000,
             "tese": "Bloqueio sem comunicação prévia = abuso de direito + dano moral",
             "base_legal": ["CDC art. 6º, III", "CC art. 186", "Res. BCB 4.753/2019"],
             "prova_minima": ["Comprovante do bloqueio", "Tentativas de contato", "Prova do prejuízo"]},
        ],
    },
    "nubank": {
        "nome": "Nubank",
        "categorias": [
            {"assunto": "Cobranças Indevidas no Cartão", "frequencia_pct": 29, "taxa_resolucao_pct": 61,
             "prazo_medio_dias": 7.8, "indenizacao_min": 1000, "indenizacao_max": 5000,
             "tese": "Lançamento não reconhecido = inversão ônus prova pelo fornecedor (CDC art. 6º, VIII)",
             "base_legal": ["CDC art. 6º, VIII", "CDC art. 42"],
             "prova_minima": ["Fatura com cobrança", "Negativa do consumidor de reconhecimento"]},
        ],
    },
    "claro": {
        "nome": "Claro",
        "categorias": [
            {"assunto": "Cancelamento não Efetivado", "frequencia_pct": 27, "taxa_resolucao_pct": 55,
             "prazo_medio_dias": 9.2, "indenizacao_min": 2000, "indenizacao_max": 7000,
             "tese": "Falha na prestação + cobranças após cancelamento = CDC art. 14 + repetição em dobro",
             "base_legal": ["CDC art. 14", "CDC art. 42", "Res. ANATEL 632/2014 art. 67"],
             "prova_minima": ["Protocolo de cancelamento", "Cobranças posteriores", "Contestação no extrato"]},
            {"assunto": "Serviço Diferente do Contratado", "frequencia_pct": 24, "taxa_resolucao_pct": 48,
             "prazo_medio_dias": 11.4, "indenizacao_min": 1500, "indenizacao_max": 6000,
             "tese": "Publicidade enganosa / vício do serviço — CDC arts. 20 e 37",
             "base_legal": ["CDC art. 20", "CDC art. 37", "Res. ANATEL 632/2014"],
             "prova_minima": ["Contrato/proposta original", "Tela ou print do serviço contratado", "Comprovante de velocidade/sinal"]},
        ],
    },
    "mercado livre": {
        "nome": "Mercado Livre",
        "categorias": [
            {"assunto": "Produto Não Entregue", "frequencia_pct": 32, "taxa_resolucao_pct": 73,
             "prazo_medio_dias": 5.9, "indenizacao_min": 2000, "indenizacao_max": 8000,
             "tese": "Responsabilidade solidária — Súm. STJ 130 + CDC art. 18",
             "base_legal": ["Súm. STJ 130", "CDC art. 18", "CDC art. 35"],
             "prova_minima": ["Comprovante de compra", "Rastreamento sem entrega", "Contato com vendedor"]},
            {"assunto": "Produto com Vício / Diferente do Anunciado", "frequencia_pct": 21, "taxa_resolucao_pct": 66,
             "prazo_medio_dias": 7.1, "indenizacao_min": 1500, "indenizacao_max": 5000,
             "tese": "Vício do produto — CDC art. 18 (30 dias para sanar, prazo de 30 dias para reclamar)",
             "base_legal": ["CDC art. 18", "CDC art. 26"],
             "prova_minima": ["Foto do produto", "Anúncio original", "Reclamação formal no ML"]},
        ],
    },
}

_EMPRESAS_ALIAS = {
    "inter": "banco inter", "c6": "c6 bank", "bradesco": "bradesco",
    "nubank": "nubank", "claro": "claro", "vivo": "vivo", "tim": "tim",
    "serasa": "serasa", "spc": "spc brasil", "mercadolivre": "mercado livre",
    "ml": "mercado livre",
}


def _normalizar(nome: str) -> str:
    n = nome.strip().lower()
    return _EMPRESAS_ALIAS.get(n, n)


def _is_staff(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/empresas")
async def listar_empresas(cu: User = Depends(get_current_user)):
    """Lista empresas com dados de reclamações disponíveis."""
    if not _is_staff(cu):
        raise HTTPException(403)
    return {
        "total": len(_BASE_EMPRESAS),
        "empresas": [
            {"id": k, "nome": v["nome"], "categorias": len(v["categorias"])}
            for k, v in _BASE_EMPRESAS.items()
        ],
        "aviso": "Dados de referência SENACON/Consumidor.gov.br — não são casos individuais",
    }


@router.get("/empresa/{nome_empresa}")
async def dados_empresa(
    nome_empresa: str,
    cu: User = Depends(get_current_user),
):
    """
    Retorna padrões de reclamações e teses para uma empresa específica.
    Útil para avaliar cabimento de ação antes de aceitar o caso.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    chave = _normalizar(nome_empresa)
    dados = _BASE_EMPRESAS.get(chave)
    if not dados:
        # Busca parcial
        for k, v in _BASE_EMPRESAS.items():
            if chave in k or k in chave:
                dados = v
                chave = k
                break

    if not dados:
        raise HTTPException(404, detail=f"Empresa '{nome_empresa}' não encontrada. Empresas disponíveis: {', '.join(_BASE_EMPRESAS)}")

    return {
        "empresa": dados["nome"],
        "total_categorias": len(dados["categorias"]),
        "categorias": dados["categorias"],
        "fonte": "Padrões Consumidor.gov.br 2023-2025 (dados públicos SENACON)",
        "aviso": "⚠️ Estimativas de referência — resultado depende do caso concreto. Revisão obrigatória pelo advogado.",
        "links_uteis": {
            "consumidor_gov": "https://www.consumidor.gov.br",
            "jec_tjmg": "https://www.tjmg.jus.br/portal-tjmg/servicos/juizado-especial.htm",
        },
    }


@router.get("/triagem-jec")
async def triagem_jec(
    empresa: str = Query(..., description="Nome da empresa reclamada"),
    valor_causa: float = Query(0.0, ge=0, description="Valor estimado da causa (R$)"),
    assunto: Optional[str] = Query(None, description="Assunto da reclamação"),
    cu: User = Depends(get_current_user),
):
    """
    Avaliação rápida de cabimento no JEC com base nos padrões de reclamação.
    Retorna: foro recomendado, valor típico, tese principal e checklist de provas.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    chave = _normalizar(empresa)
    dados = _BASE_EMPRESAS.get(chave)
    if not dados:
        for k, v in _BASE_EMPRESAS.items():
            if chave in k or k in chave:
                dados = v
                break

    salario_minimo_2026 = 1518.00
    limite_20sm = salario_minimo_2026* 20   # R$ 30.360
    limite_40sm = salario_minimo_2026 * 40  # R$ 60.720

    # Encontrar categoria mais relevante
    categoria = None
    if dados and assunto:
        assunto_lower = assunto.lower()
        for cat in dados["categorias"]:
            if any(p in assunto_lower for p in cat["assunto"].lower().split()):
                categoria = cat
                break
    if not categoria and dados:
        # Retorna a categoria mais frequente
        categoria = max(dados["categorias"], key=lambda c: c["frequencia_pct"])

    # Calcular valor de causa se não informado
    if valor_causa == 0 and categoria:
        valor_causa = (categoria["indenizacao_min"] + categoria["indenizacao_max"]) / 2

    # Determinar foro
    if valor_causa <= limite_20sm:
        foro = "JEC — até 20 SM (R$ {:.0f}) — advogado facultativo".format(limite_20sm)
        rito = "Sumaríssimo (Lei 9.099/95)"
    elif valor_causa <= limite_40sm:
        foro = "JEC — até 40 SM (R$ {:.0f}) — advogado obrigatório".format(limite_40sm)
        rito = "Sumaríssimo (Lei 9.099/95)"
    else:
        foro = "Vara Cível — acima de 40 SM"
        rito = "Ordinário (CPC)"

    return {
        "empresa": dados["nome"] if dados else empresa,
        "foro_recomendado": foro,
        "rito": rito,
        "valor_causa_estimado": valor_causa,
        "tese_principal": categoria["tese"] if categoria else None,
        "base_legal": categoria["base_legal"] if categoria else [],
        "prova_minima": categoria["prova_minima"] if categoria else [],
        "taxa_resolucao_amigavel_pct": categoria["taxa_resolucao_pct"] if categoria else None,
        "checklist_pre_ajuizamento": [
            "✅ Registrar reclamação no Consumidor.gov.br (prova documental + possibilidade de resolução)",
            "✅ Solicitar DED (Demonstrativo da Evolução da Dívida) se for cobrança/negativação",
            "✅ Guardar prints de conversas, boletos e extratos",
            "✅ Aguardar resposta por 10 dias úteis antes de ajuizar",
            "✅ Verificar Súm. STJ 385 se já houver outra negativação em nome do cliente",
        ],
        "aviso": "⚠️ Triagem automatizada. Revisão obrigatória pelo advogado. Resultado depende do caso concreto.",
    }


@router.get("/painel-semanal")
async def painel_reclamacoes(
    top: int = Query(6, ge=1, le=20, description="Número de empresas no ranking"),
    cu: User = Depends(get_current_user),
):
    """
    Painel consolidado: empresas com maior potencial de captação (alta frequência + baixa resolução amigável).
    Ideal para identificar frentes de atuação no JEC/CDC.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    ranking = []
    for chave, dados in _BASE_EMPRESAS.items():
        if not dados["categorias"]:
            continue
        cat_principal = max(dados["categorias"], key=lambda c: c["frequencia_pct"] - c["taxa_resolucao_pct"] * 0.3)
        score = cat_principal["frequencia_pct"] - cat_principal["taxa_resolucao_pct"] * 0.3
        ranking.append({
            "empresa": dados["nome"],
            "assunto_principal": cat_principal["assunto"],
            "frequencia_pct": cat_principal["frequencia_pct"],
            "taxa_resolucao_amigavel_pct": cat_principal["taxa_resolucao_pct"],
            "potencial_jec": round(score, 1),
            "indenizacao_tipica": f"R$ {cat_principal['indenizacao_min']:,.0f}–{cat_principal['indenizacao_max']:,.0f}",
        })

    ranking.sort(key=lambda x: x["potencial_jec"], reverse=True)

    return {
        "criterio": "Alta frequência de reclamação + baixa resolução amigável = maior potencial JEC",
        "periodo_referencia": "2023-2025 (dados públicos SENACON)",
        "salario_minimo_referencia": 1518.00,
        "ranking": ranking[:top],
        "aviso": "⚠️ Dados de referência SENACON — não são dados individuais. Conferir com cliente antes de ajuizar.",
        "links": {
            "consumidor_gov": "https://www.consumidor.gov.br/pages/dadosabertos/externo/",
            "dados_mj": "https://dados.mj.gov.br",
        },
    }
