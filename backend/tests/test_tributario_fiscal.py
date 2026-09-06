"""Vertical Tributário — leitor de XML fiscal + pré-auditoria determinística.

Cobertura:
  • parser NF-e: campos, Decimal, fail-soft e dedupe;
  • Tema 69: cálculo conferível, modulação e incompatibilidade com Simples;
  • monofásicos: radar de NCM e estimativa preliminar;
  • NF-e antiga NÃO é descartada nem chamada de prescrita pela data de emissão;
  • ICMS-ST: radar sem inventar valor;
  • consolidação valida contra o schema de resposta;
  • endpoint: guarda de >50 arquivos e hardening de lote/PDF.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.fiscal.nfe_parser import parse_lote, parse_nfe
from app.services.fiscal.recuperacao_creditos import analisar_recuperacao


HOJE = date(2026, 7, 5)  # data fixa para referência documental reproduzível


def _mk_nfe(dh_emi: str, itens: list[dict], chave: str, crt: str = "3") -> str:
    """Monta um nfeProc mínimo válido. `itens`: [{ncm, cfop, vprod, vicms?}]."""
    dets = []
    v_nf = Decimal("0")
    for i, it in enumerate(itens, start=1):
        v_nf += Decimal(str(it["vprod"]))
        icms = ""
        if it.get("vicms") is not None:
            icms = (
                f"<ICMS><ICMS00><CST>00</CST>"
                f"<vICMS>{it['vicms']}</vICMS></ICMS00></ICMS>"
            )
        dets.append(
            f"<det nItem='{i}'>"
            f"<prod><xProd>Item {i}</xProd><NCM>{it['ncm']}</NCM>"
            f"<CFOP>{it['cfop']}</CFOP><vProd>{it['vprod']}</vProd></prod>"
            f"<imposto>{icms}"
            f"<PIS><PISAliq><vPIS>0.00</vPIS></PISAliq></PIS>"
            f"<COFINS><COFINSAliq><vCOFINS>0.00</vCOFINS></COFINSAliq></COFINS>"
            f"</imposto></det>"
        )
    return (
        "<nfeProc xmlns='http://www.portalfiscal.inf.br/nfe' versao='4.00'><NFe>"
        f"<infNFe Id='NFe{chave}' versao='4.00'>"
        f"<ide><nNF>123</nNF><serie>1</serie><dhEmi>{dh_emi}</dhEmi></ide>"
        "<emit><CNPJ>12345678000199</CNPJ><xNome>Cliente Teste LTDA</xNome>"
        f"<CRT>{crt}</CRT><enderEmit><UF>MG</UF></enderEmit></emit>"
        "<dest><CNPJ>99887766000155</CNPJ><xNome>Comprador SA</xNome>"
        "<enderDest><UF>SP</UF></enderDest></dest>"
        + "".join(dets)
        + f"<total><ICMSTot><vNF>{v_nf}</vNF></ICMSTot></total>"
        "</infNFe></NFe></nfeProc>"
    )


CHAVE_A = "1" * 44
CHAVE_B = "2" * 44
ITENS_PADRAO = [
    {"ncm": "30049099", "cfop": "5102", "vprod": "1000.00", "vicms": "120.00"},
    {"ncm": "84713012", "cfop": "5102", "vprod": "2000.00", "vicms": "360.00"},
]


# ══════════════════════════════════════════════════════════════════════════
# Parser
# ══════════════════════════════════════════════════════════════════════════
def test_parser_extrai_campos_em_decimal():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    assert nota["erro"] is None
    assert nota["chave_acesso"] == CHAVE_A and len(nota["chave_acesso"]) == 44
    assert nota["numero"] == "123"
    assert nota["data_emissao"] == date(2024, 3, 1)
    assert nota["emitente"]["nome"] == "Cliente Teste LTDA"
    assert nota["emitente"]["crt"] == "3"
    assert nota["valor_total"] == Decimal("3000.00")
    assert isinstance(nota["valor_total"], Decimal)
    assert len(nota["itens"]) == 2
    assert nota["itens"][0]["ncm"] == "30049099"
    assert nota["itens"][0]["vicms"] == Decimal("120.00")


def test_parser_fail_soft_xml_invalido():
    nota = parse_nfe("<isto> nao é </nfe", arquivo="ruim.xml")
    assert nota["erro"] and nota["arquivo"] == "ruim.xml"


def test_parser_rejeita_nao_nfe():
    nota = parse_nfe("<html><body>oi</body></html>", arquivo="pagina.xml")
    assert nota["erro"] and "NF-e" in nota["erro"]


def test_parse_lote_dedup_por_chave():
    xml = _mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A)
    notas = parse_lote([("a.xml", xml.encode()), ("copia.xml", xml.encode())])
    assert len(notas) == 2
    assert notas[0]["erro"] is None
    assert notas[1]["erro"] and "duplicada" in notas[1]["erro"].lower()


# ══════════════════════════════════════════════════════════════════════════
# Tema 69 STF
# ══════════════════════════════════════════════════════════════════════════
def _tese(res: dict, tese_id: str) -> dict:
    return next(t for t in res["teses"] if t["tese_id"] == tese_id)


def test_tema69_lucro_real_conferivel():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "tema_69_stf")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == pytest.approx(44.40, abs=1e-6)
    assert t["memoria_calculo"]
    assert any("Elegibilidade e prescrição NÃO foram avaliadas" in a for a in t["alertas"])


def test_tema69_lucro_presumido_conferivel():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_presumido", hoje=HOJE)
    assert _tese(res, "tema_69_stf")["valor_estimado"] == pytest.approx(17.52, abs=1e-6)


def test_tema69_inaplicavel_no_simples():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "simples", hoje=HOJE)
    t = _tese(res, "tema_69_stf")
    assert t["aplicavel"] is False
    assert t["valor_estimado"] == 0.0
    assert "Simples" in (t["motivo_inaplicavel"] or "")


def test_tema69_modulacao_exclui_nota_anterior_a_2017():
    boa = parse_nfe(_mk_nfe("2018-06-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    velha = parse_nfe(_mk_nfe("2016-06-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_B))
    res = analisar_recuperacao([boa, velha], "lucro_real", hoje=date(2020, 1, 1))
    t = _tese(res, "tema_69_stf")
    assert t["valor_estimado"] == pytest.approx(44.40, abs=1e-6)
    assert res["notas_prescritas"] == 0
    assert any("15/03/2017" in a or "modula" in a.lower() for a in t["alertas"])


# ══════════════════════════════════════════════════════════════════════════
# Monofásicos (Simples)
# ══════════════════════════════════════════════════════════════════════════
def test_monofasico_so_conta_item_com_ncm_monofasico():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "simples", hoje=HOJE)
    t = _tese(res, "monofasicos_simples")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == pytest.approx(6.20, abs=1e-6)
    assert any("Elegibilidade e prescrição NÃO foram avaliadas" in a for a in t["alertas"])


def test_monofasico_inaplicavel_fora_do_simples():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "monofasicos_simples")
    assert t["aplicavel"] is False
    assert t["valor_estimado"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# ICMS-ST e gate de prescrição
# ══════════════════════════════════════════════════════════════════════════
def test_icms_st_radar_sem_valor_inventado():
    itens = [{"ncm": "84719999", "cfop": "5405", "vprod": "500.00", "vicms": None}]
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", itens, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "icms_st_ressarcimento")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == 0.0
    assert any("apuração" in a.lower() or "revisão" in a.lower() for a in t["alertas"])


def test_nfe_antiga_nao_e_descartada_nem_chamada_de_prescrita():
    # Emissão em 2019 é anterior à referência documental de 5 anos em HOJE,
    # mas emissão da NF-e não é termo universal do CTN art. 168.
    velha = parse_nfe(_mk_nfe("2019-05-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([velha], "lucro_real", hoje=HOJE)

    # A estimativa matemática permanece; somente a modulação específica do
    # Tema 69 poderia excluir uma nota por data nesse radar.
    assert _tese(res, "tema_69_stf")["valor_estimado"] == pytest.approx(44.40, abs=1e-6)
    assert res["notas_prescritas"] == 0
    assert any("PRESCRIÇÃO NÃO AVALIADA" in a for a in res["alertas_globais"])
    assert any("Permaneceram na estimativa" in a for a in res["alertas_globais"])
    assert not any("excluída(s) de todas as somas" in a for a in res["alertas_globais"])


# ══════════════════════════════════════════════════════════════════════════
# Consolidação — contrato + schema
# ══════════════════════════════════════════════════════════════════════════
def test_consolidacao_valida_contra_schema_de_resposta():
    from app.routers.tributario_fiscal import ConsolidacaoOut

    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    ruim = {"arquivo": "x.xml", "erro": "XML inválido"}
    res = analisar_recuperacao([nota, ruim], "lucro_real", hoje=HOJE)

    assert isinstance(res["notas_com_erro"], int) and res["notas_com_erro"] == 1
    assert res["notas_analisadas"] == 1
    assert res["notas_prescritas"] == 0
    assert isinstance(res["notas"], list) and len(res["notas"]) == 2
    assert any(n["erro"] for n in res["notas"])
    assert all(isinstance(t["base_legal"], str) for t in res["teses"])
    assert res["periodo"]["inicio"] == "2024-03-01"

    out = ConsolidacaoOut.model_validate(res)
    assert out.total_estimado == pytest.approx(44.40, abs=1e-6)
    assert out.notas_com_erro == 1
    assert out.notas_prescritas == 0


# ══════════════════════════════════════════════════════════════════════════
# Endpoint — guarda de limite
# ══════════════════════════════════════════════════════════════════════════
async def test_endpoint_recusa_mais_de_50_arquivos():
    from fastapi import HTTPException
    from app.routers.tributario_fiscal import analisar_xml

    with pytest.raises(HTTPException) as exc:
        await analisar_xml(arquivos=[object()] * 51, regime="simples", cu=None)
    assert exc.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# Hardening
# ══════════════════════════════════════════════════════════════════════════
class _FakeUpload:
    def __init__(self, filename: str, dados: bytes):
        self.filename = filename
        self._buf = dados
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._buf) - self._pos
        chunk = self._buf[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


async def test_lote_respeita_teto_agregado_de_bytes(monkeypatch):
    from app.routers import tributario_fiscal as trib

    monkeypatch.setattr(trib, "MAX_LOTE_MB", 1)
    recheio = b"<!--" + b"x" * (450 * 1024) + b"-->"
    grande = _mk_nfe(
        "2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A
    ).encode() + recheio
    arquivos = [_FakeUpload(f"{i}.xml", grande) for i in range(3)]
    res = await trib.analisar_xml(arquivos=arquivos, regime="lucro_real", cu=None)
    assert any(n.erro and "Lote excede" in n.erro for n in res.notas)


def test_schema_rejeita_payload_de_pdf_gigante():
    from pydantic import ValidationError
    from app.routers.tributario_fiscal import ConsolidacaoOut

    base = {
        "regime": "lucro_real",
        "total_estimado": 0.0,
        "notas_analisadas": 0,
        "notas_com_erro": 0,
        "notas_prescritas": 0,
        "periodo": {"inicio": None, "fim": None},
        "teses": [],
        "alertas_globais": [],
        "aviso_hitl": "ok",
        "notas": [],
    }
    demais = dict(base, teses=[{
        "tese_id": "t",
        "titulo": "x",
        "base_legal": "y",
        "fundamento": "z",
        "aplicavel": False,
        "valor_estimado": 0.0,
        "memoria_calculo": [],
        "alertas": [],
        "nivel_confianca": "estimativa_preliminar",
    }] * 21)
    with pytest.raises(ValidationError):
        ConsolidacaoOut.model_validate(demais)
