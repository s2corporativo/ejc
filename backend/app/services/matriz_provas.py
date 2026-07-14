# ── app/services/matriz_provas.py ─────────────────────────────────────────────
# Matriz tese×prova — REFERÊNCIA ESTÁTICA determinística (Fase C).
#
# Para cada tese/pedido típico (por área ou "geral"), a lista de provas MÍNIMAS
# recomendadas para instruir a pretensão. É um PISO determinístico, sem IA e sem
# migration: ancora a sugestão de provas (routers/provas.py) e reforça as provas
# faltantes da Ficha de Triagem (ficha_triagem_service.py).
#
# Invariantes:
#   • funções puras (sem rede/DB/estado); NUNCA levantam exceção;
#   • casamento tolerante a acento/caixa (normalização unicode + lower);
#   • dedup por tese e por prova; nada de PII (só rótulos jurídicos genéricos).
from __future__ import annotations

import unicodedata

# Entrada da matriz: cada dict tem
#   tese   — rótulo legível da tese/pedido (chave de dedup)
#   termos — palavras-chave (normalizadas em runtime) que casam texto livre
#   provas — provas mínimas recomendadas (ordem = prioridade)
_Entrada = dict[str, list[str] | str]

# Área ("geral" aplica a todas) → lista de teses típicas com suas provas mínimas.
# A chave de área segue AREAS_DIREITO (peca_service.AREAS_DIREITO).
MATRIZ: dict[str, list[_Entrada]] = {
    # ── Teses transversais (valem para qualquer área) ──────────────────────────
    "geral": [
        {
            "tese": "Dano material",
            "termos": ["dano material", "danos materiais", "prejuizo material",
                       "prejuizos materiais", "reparacao material", "ressarcimento",
                       "reembolso", "lucros cessantes", "danos emergentes"],
            "provas": ["Nota fiscal", "Recibo", "Comprovante de pagamento",
                       "Orçamento"],
        },
        {
            "tese": "Dano moral",
            "termos": ["dano moral", "danos morais", "abalo moral",
                       "dano extrapatrimonial", "abalo psicologico",
                       "sofrimento", "constrangimento"],
            "provas": ["Documentos que comprovem o fato",
                       "Prova do nexo causal (documentos)",
                       "Boletim de ocorrência / registro",
                       "Testemunhas"],
        },
    ],
    # ── Consumidor ─────────────────────────────────────────────────────────────
    "consumidor": [
        {
            "tese": "Falha na prestação do serviço",
            "termos": ["falha na prestacao", "falha do servico", "falha no servico",
                       "vicio do servico", "defeito do servico", "ma prestacao",
                       "servico defeituoso", "falha no atendimento",
                       "servico nao prestado"],
            "provas": ["Contrato de prestação de serviço",
                       "Protocolos de atendimento",
                       "Mensagens / e-mails trocados",
                       "Reclamações registradas (SAC, Procon, consumidor.gov)"],
        },
        {
            "tese": "Vício do produto",
            "termos": ["vicio do produto", "produto com defeito", "defeito do produto",
                       "produto viciado", "produto com vicio"],
            "provas": ["Nota fiscal", "Termo de garantia",
                       "Ordem de serviço da assistência técnica",
                       "Fotos / laudo do defeito"],
        },
        {
            "tese": "Cobrança indevida",
            "termos": ["cobranca indevida", "cobrado indevidamente", "cobranca abusiva",
                       "repeticao de indebito", "devolucao em dobro",
                       "valor indevido", "debito indevido"],
            "provas": ["Fatura / boleto", "Comprovante de pagamento",
                       "Extrato", "Contrato"],
        },
    ],
    # ── Cível ──────────────────────────────────────────────────────────────────
    "civil": [
        {
            "tese": "Falha na prestação do serviço",
            "termos": ["falha na prestacao", "falha do servico", "falha no servico",
                       "vicio do servico", "defeito do servico", "ma prestacao",
                       "servico defeituoso", "servico nao prestado"],
            "provas": ["Contrato de prestação de serviço",
                       "Protocolos de atendimento",
                       "Mensagens / e-mails trocados",
                       "Reclamações / notificações"],
        },
        {
            "tese": "Inadimplemento contratual",
            "termos": ["inadimplemento", "descumprimento contratual",
                       "descumprimento do contrato", "quebra de contrato",
                       "nao cumprimento", "cobranca de divida", "execucao de titulo"],
            "provas": ["Contrato", "Comprovantes de pagamento",
                       "Notificação extrajudicial", "Mensagens / e-mails"],
        },
        {
            "tese": "Responsabilidade civil",
            "termos": ["responsabilidade civil", "ato ilicito", "indenizacao por",
                       "acidente", "reparacao de danos"],
            "provas": ["Prova do ato ilícito", "Prova do dano",
                       "Prova do nexo causal", "Testemunhas"],
        },
    ],
    # ── Bancário ───────────────────────────────────────────────────────────────
    "bancario": [
        {
            "tese": "Juros / tarifas abusivos",
            "termos": ["juros abusivos", "juros abusiv", "tarifa abusiva",
                       "tarifas abusivas", "encargos abusivos", "capitalizacao",
                       "anatocismo", "juros remuneratorios", "revisao de contrato",
                       "revisao contratual", "revisional"],
            "provas": ["Contrato bancário",
                       "Planilha evolutiva do débito",
                       "Extrato da conta / do débito",
                       "Perícia contábil"],
        },
        {
            "tese": "Cobrança indevida / débito automático",
            "termos": ["cobranca indevida", "desconto indevido", "debito automatico",
                       "emprestimo nao contratado", "fraude bancaria"],
            "provas": ["Extrato bancário", "Contrato",
                       "Comprovantes de desconto", "Boletim de ocorrência"],
        },
    ],
    # ── Previdenciário ─────────────────────────────────────────────────────────
    "previdenciario": [
        {
            "tese": "Incapacidade laboral",
            "termos": ["incapacidade laboral", "incapacidade para o trabalho",
                       "auxilio-doenca", "auxilio doenca", "aposentadoria por invalidez",
                       "beneficio por incapacidade", "incapacidade"],
            "provas": ["Laudos médicos", "Exames", "Prontuários médicos",
                       "CAT (Comunicação de Acidente de Trabalho)"],
        },
        {
            "tese": "Revisão de benefício",
            "termos": ["revisao de beneficio", "revisao do beneficio",
                       "revisao da aposentadoria", "recalculo do beneficio",
                       "revisao da rmi", "revisao da renda"],
            "provas": ["CNIS", "Carta de concessão do benefício",
                       "Cálculos / memória de cálculo",
                       "Histórico de contribuições"],
        },
    ],
    # ── Trabalhista ────────────────────────────────────────────────────────────
    "trabalhista": [
        {
            "tese": "Horas extras",
            "termos": ["horas extras", "hora extra", "jornada extraordinaria",
                       "sobrejornada", "banco de horas", "labor extraordinario"],
            "provas": ["Cartões de ponto", "Controles de jornada",
                       "Testemunhas", "Escala de trabalho"],
        },
        {
            "tese": "Rescisão indireta",
            "termos": ["rescisao indireta", "falta grave do empregador", "art. 483",
                       "justa causa do empregador"],
            "provas": ["Provas da falta grave do empregador",
                       "Mensagens / e-mails / áudios",
                       "Testemunhas",
                       "Documentos internos (advertências, comunicados)"],
        },
        {
            "tese": "Incapacidade laboral / acidente de trabalho",
            "termos": ["incapacidade laboral", "acidente de trabalho", "doenca ocupacional",
                       "doenca do trabalho", "incapacidade"],
            "provas": ["Laudos médicos", "Exames", "Prontuários médicos",
                       "CAT (Comunicação de Acidente de Trabalho)"],
        },
        {
            "tese": "Assédio moral",
            "termos": ["assedio moral", "assedio", "dano moral trabalhista"],
            "provas": ["Testemunhas", "Mensagens / e-mails / áudios",
                       "Registros de atendimento médico / psicológico",
                       "Boletim de ocorrência"],
        },
    ],
    # ── Administrativo ─────────────────────────────────────────────────────────
    "administrativo": [
        {
            "tese": "Nulidade de ato administrativo",
            "termos": ["nulidade de ato administrativo", "nulidade do ato",
                       "ato administrativo nulo", "vicio do ato administrativo",
                       "anulacao do ato", "ilegalidade do ato"],
            "provas": ["Processo administrativo integral",
                       "Comprovante de ciência / intimação",
                       "Publicação do ato (diário oficial)",
                       "Documentos que demonstrem o vício"],
        },
    ],
}


def _norm(texto: object) -> str:
    """lower + remoção de acentos (NFKD). Robusto a None/tipos inesperados."""
    if not isinstance(texto, str):
        texto = "" if texto is None else str(texto)
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def _entradas_para(area: object) -> list[_Entrada]:
    """Entradas aplicáveis: as da área específica + as 'geral' (nesta ordem)."""
    chave = _norm(area).strip()
    especificas = MATRIZ.get(chave, []) if chave and chave != "geral" else []
    return list(especificas) + list(MATRIZ.get("geral", []))


def provas_recomendadas(area: object, texto_pedidos: object) -> list[dict]:
    """Casa os pedidos/tese (texto livre) contra a matriz da área + 'geral'.

    Retorna ``[{"tese": <rótulo>, "provas": [<str>, ...]}]`` deduplicado por tese
    (mantém a 1ª ocorrência) e por prova dentro de cada tese. Nunca levanta
    exceção; texto sem match → ``[]``.
    """
    try:
        alvo = _norm(texto_pedidos)
        if not alvo.strip():
            return []
        saida: list[dict] = []
        teses_vistas: set[str] = set()
        for entrada in _entradas_para(area):
            tese = entrada.get("tese")
            termos = entrada.get("termos") or []
            provas = entrada.get("provas") or []
            if not isinstance(tese, str) or tese in teses_vistas:
                continue
            if not any(_norm(t) in alvo for t in termos if isinstance(t, str)):
                continue
            # dedup de provas preservando ordem
            vistas: set[str] = set()
            provas_dedup = [p for p in provas
                            if isinstance(p, str) and not (p in vistas or vistas.add(p))]
            if not provas_dedup:
                continue
            teses_vistas.add(tese)
            saida.append({"tese": tese, "provas": provas_dedup})
        return saida
    except Exception:  # referência estática NUNCA derruba o chamador
        return []


def provas_recomendadas_texto(area: object, texto_pedidos: object) -> str:
    """Resumo compacto (uma linha por tese) para injeção em prompt.

    Formato: ``Tese: prova1, prova2 | Outra tese: prova3``. Sem PII — apenas
    rótulos jurídicos genéricos. Input vazio / sem match → ``""``.
    """
    try:
        recs = provas_recomendadas(area, texto_pedidos)
        return " | ".join(
            f"{r['tese']}: {', '.join(r['provas'])}" for r in recs
        )
    except Exception:
        return ""
