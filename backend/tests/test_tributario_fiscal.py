"""Vertical Tributário — leitor de XML fiscal (NF-e) + motor determinístico de
recuperação de créditos.

Cobertura:
  • parser NF-e: campos extraídos, Decimal, fail-soft de XML inválido, dedupe;
  • Tema 69 STF: caso conferível à mão (lucro real/presumido), modulação
    15/03/2017, inaplicável ao Simples;
  • monofásicos: só o item de NCM monofásico entra na receita; inaplicável fora
    do Simples;
  • prescrição (CTN 168, I): nota fora da janela de 5 anos sai das somas;
  • ICMS-ST: radar (aplicável, valor 0, alerta pedindo GIAs);
  • consolidação valida contra o schema de resposta (ConsolidacaoOut);
  • endpoint: guarda de >50 arquivos (422).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.fiscal.nfe_parser import parse_nfe, parse_lote
from app.services.fiscal.recuperacao_creditos import analisar_recuperacao


HOJE = date(2026, 7, 5)  # fixa a janela de prescrição (corte = 2021-07-05)


# ── Builder de XML de NF-e (namespace default do portal fiscal) ────────────────

def _mk_nfe(dh_emi: str, itens: list[dict], chave: str, crt: str = "3") -> str:
    """Monta um nfeProc mínimo válido. `itens`: [{ncm, cfop, vprod, vicms?}]."""
    dets = []
    v_nf = Decimal("0")
    for i, it in enumerate(itens, start=1):
        v_nf += Decimal(str(it["vprod"]))
        icms = ""
        if it.get("vicms") is not None:
            icms = (f"<ICMS><ICMS00><CST>00</CST>"
                    f"<vICMS>{it['vicms']}</vICMS></ICMS00></ICMS>")
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

# Nota "padrão": item monofásico (medicamento) + item normal, ambos saída não-ST.
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
    # não lança — o lote continua


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
    # ICMS destacado nas saídas = 120 + 360 = 480; 480 × 9,25% = 44,40.
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "tema_69_stf")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == pytest.approx(44.40, abs=1e-6)
    assert t["memoria_calculo"]


def test_tema69_lucro_presumido_conferivel():
    # 480 × 3,65% = 17,52.
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
    # Para isolar a modulação da prescrição, ancora "hoje" em 2020 (corte 2015):
    # ambas as notas estão dentro da janela de 5 anos, mas só a modulação
    # (15/03/2017) deve excluir a de 2016.
    hoje = date(2020, 1, 1)
    boa = parse_nfe(_mk_nfe("2018-06-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    velha = parse_nfe(_mk_nfe("2016-06-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_B))
    res = analisar_recuperacao([boa, velha], "lucro_real", hoje=hoje)
    t = _tese(res, "tema_69_stf")
    # só a nota de 2018 conta → 44,40, e há alerta de modulação
    assert t["valor_estimado"] == pytest.approx(44.40, abs=1e-6)
    assert res["notas_prescritas"] == 0
    assert any("15/03/2017" in a or "modula" in a.lower() for a in t["alertas"])


# ══════════════════════════════════════════════════════════════════════════
# Monofásicos (Simples)
# ══════════════════════════════════════════════════════════════════════════
def test_monofasico_so_conta_item_com_ncm_monofasico():
    # item 1 (NCM 3004) entra; item 2 (NCM 8471) não.
    # receita_mono = 1000 ; parcela = 4% × 15,50% = 0,62% → 6,20.
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "simples", hoje=HOJE)
    t = _tese(res, "monofasicos_simples")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == pytest.approx(6.20, abs=1e-6)


def test_monofasico_inaplicavel_fora_do_simples():
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "monofasicos_simples")
    assert t["aplicavel"] is False
    assert t["valor_estimado"] == 0.0


# ══════════════════════════════════════════════════════════════════════════
# ICMS-ST (radar) e prescrição
# ══════════════════════════════════════════════════════════════════════════
def test_icms_st_radar_sem_valor_inventado():
    itens = [{"ncm": "84719999", "cfop": "5405", "vprod": "500.00", "vicms": None}]
    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", itens, CHAVE_A))
    res = analisar_recuperacao([nota], "lucro_real", hoje=HOJE)
    t = _tese(res, "icms_st_ressarcimento")
    assert t["aplicavel"] is True
    assert t["valor_estimado"] == 0.0
    assert any("GIA" in a or "ressarcimento" in a.lower() for a in t["alertas"])


def test_prescricao_exclui_nota_fora_da_janela_5_anos():
    # nota de 2019 (< corte 2021-07-05) sai das somas do Tema 69.
    velha = parse_nfe(_mk_nfe("2019-05-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    res = analisar_recuperacao([velha], "lucro_real", hoje=HOJE)
    assert _tese(res, "tema_69_stf")["valor_estimado"] == 0.0
    assert res["notas_prescritas"] == 1
    assert any("168" in a or "5 anos" in a for a in res["alertas_globais"])


# ══════════════════════════════════════════════════════════════════════════
# Consolidação — shape do contrato + schema de resposta
# ══════════════════════════════════════════════════════════════════════════
def test_consolidacao_valida_contra_schema_de_resposta():
    from app.routers.tributario_fiscal import ConsolidacaoOut

    nota = parse_nfe(_mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO, CHAVE_A))
    ruim = {"arquivo": "x.xml", "erro": "XML inválido"}
    res = analisar_recuperacao([nota, ruim], "lucro_real", hoje=HOJE)

    # contrato consumido pelo frontend
    assert isinstance(res["notas_com_erro"], int) and res["notas_com_erro"] == 1
    assert res["notas_analisadas"] == 1
    assert isinstance(res["notas"], list) and len(res["notas"]) == 2
    assert any(n["erro"] for n in res["notas"])
    assert all(isinstance(t["base_legal"], str) for t in res["teses"])
    assert res["periodo"]["inicio"] == "2024-03-01"

    # valida contra o Pydantic da rota (o mesmo do response_model)
    out = ConsolidacaoOut.model_validate(res)
    assert out.total_estimado == pytest.approx(44.40, abs=1e-6)
    assert out.notas_com_erro == 1


# ══════════════════════════════════════════════════════════════════════════
# Endpoint — guarda de limite de arquivos
# ══════════════════════════════════════════════════════════════════════════
async def test_endpoint_recusa_mais_de_50_arquivos():
    from fastapi import HTTPException

    from app.routers.tributario_fiscal import analisar_xml

    # a guarda dispara por len() antes de ler qualquer arquivo → dummies servem
    with pytest.raises(HTTPException) as exc:
        await analisar_xml(arquivos=[object()] * 51, regime="simples", cu=None)
    assert exc.value.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# Hardening (achados da auditoria de segurança)
# ══════════════════════════════════════════════════════════════════════════
class _FakeUpload:
    """UploadFile mínimo: serve `dados` em blocos via read(size), como o
    Starlette faz — sem depender de spool real."""

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

    # encolhe o teto do lote para 1 MB (cada arquivo ~450 KB fica abaixo do
    # teto POR ARQUIVO, mas três somados estouram o teto AGREGADO).
    monkeypatch.setattr(trib, "MAX_LOTE_MB", 1)
    recheio = b"<!--" + b"x" * (450 * 1024) + b"-->"
    grande = _mk_nfe("2024-03-01T10:00:00-03:00", ITENS_PADRAO,
                     CHAVE_A).encode() + recheio
    arquivos = [_FakeUpload(f"{i}.xml", grande) for i in range(3)]
    res = await trib.analisar_xml(arquivos=arquivos, regime="lucro_real", cu=None)
    # ao menos o último é rejeitado pelo teto agregado (vira nota com erro)
    assert any(n.erro and "Lote excede" in n.erro for n in res.notas)


def test_schema_rejeita_payload_de_pdf_gigante():
    from pydantic import ValidationError

    from app.routers.tributario_fiscal import ConsolidacaoOut

    base = {
        "regime": "lucro_real", "total_estimado": 0.0, "notas_analisadas": 0,
        "notas_com_erro": 0, "notas_prescritas": 0,
        "periodo": {"inicio": None, "fim": None},
        "teses": [], "alertas_globais": [], "aviso_hitl": "ok", "notas": [],
    }
    # 21 teses > teto de 20 → rejeitado antes de chegar ao WeasyPrint
    demais = dict(base, teses=[{
        "tese_id": "t", "titulo": "x", "base_legal": "y", "fundamento": "z",
        "aplicavel": False, "valor_estimado": 0.0, "memoria_calculo": [],
        "alertas": [], "nivel_confianca": "estimativa_preliminar",
    }] * 21)
    with pytest.raises(ValidationError):
        ConsolidacaoOut.model_validate(demais)
